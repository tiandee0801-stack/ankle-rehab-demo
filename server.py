#!/usr/bin/env python3
"""Local-only ankle rehab product demonstration. Stdlib HTTP + SQLite.

Pose inference runs in the already-installed MMPose environment, isolated from
the HTTP process. All business decisions remain explicitly human-reviewed.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('ANKLE_DATA_DIR', str(ROOT / 'data'))).resolve()
DIST = ROOT / 'dist'
PYTHON = Path(os.environ.get('ANKLE_MODEL_PYTHON', str(Path.home() / 'Documents/运动健身资料/mmpose-main/.venv/bin/python')))
ENGINE = ROOT / 'engine' / 'analyze_video.py'
MAX_UPLOAD = 80 * 1024 * 1024
LOCK = threading.Lock()
DB_LOCK = threading.RLock()
BUSY = False
DB = DATA / 'ankle.sqlite3'
VERSION = '0.1.0'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')

def uid(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16]

def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    return db

def objects(kind):
    with DB_LOCK, connect() as db:
        return [json.loads(r[0]) for r in db.execute('SELECT body FROM objects WHERE kind=? ORDER BY created,id', (kind,))]

def get(kind, ident):
    with DB_LOCK, connect() as db:
        row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, ident)).fetchone()
    if not row:
        raise ValueError('找不到这条记录，请刷新后重试。')
    return json.loads(row[0])

def put(kind, obj):
    with DB_LOCK, connect() as db:
        db.execute('INSERT INTO objects(kind,id,body,created) VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',
                   (kind, obj['id'], json.dumps(obj, ensure_ascii=False, allow_nan=False), obj.get('createdAt', now())))
    return obj

def textfield(value, name, limit=2000, required=False):
    if not isinstance(value, str):
        raise ValueError(name + '需要填写文字。')
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(name + ('不能为空。' if not value else '过长。'))
    return value

def choice(value, allowed, name):
    if value not in allowed:
        raise ValueError(name + '选项无效。')
    return value

def boolfield(value, name):
    if not isinstance(value, bool):
        raise ValueError(name + '需要明确选择。')
    return value

def candidate(profile, record):
    reasons = []
    priority = 'Routine'
    if profile['screening']['redFlags']:
        reasons.append('筛查中存在需要优先人工确认的信息。')
        priority = 'Attention'
    if not profile['screening']['cleared']:
        reasons.append('尚未确认可执行范围，请先人工核对。')
        if priority != 'Attention': priority = 'Review'
    if profile.get('intakeStatus') != 'confirmed':
        reasons.append('档案尚未经过人工确认。')
        if priority != 'Attention': priority = 'Review'
    baseline = record['t0']['pain']
    for key, label in [('t1', '训练中'), ('t2', '训练后'), ('t3', '次日')]:
        item = record.get(key)
        if item and (item['pain'] > baseline or item['swelling'] == 'increased'):
            reasons.append(label + '反馈有增加，需人工复核。')
            if priority != 'Attention': priority = 'Review'
    missing = record.get('t3') is None
    if missing:
        reasons.append('次日反馈待补齐；当前记录不代表完整训练反应。')
        if priority != 'Attention': priority = 'Review'
    if not reasons:
        reasons.append('已记录四个时点；未触发本 Demo 的复核提示，仍需人工判断阶段。')
    return {'priority': priority, 'reasons': reasons, 'missingNextDay': missing}

def valid_profile(body, previous=None):
    old = previous or {}
    b = {**old, **body}
    s = b.get('screening')
    if not isinstance(s, dict): raise ValueError('请填写筛查信息。')
    obj = {
        'id': old.get('id', uid('profile')),
        'name': textfield(b.get('name', ''), '称呼', 40, True),
        'side': choice(b.get('side'), ['left', 'right', 'both'], '关注侧'),
        'route': choice(b.get('route'), ['surgery', 'conservative', 'unsure'], '恢复路线'),
        'goal': textfield(b.get('goal', ''), '目标', 500, True),
        'product': choice(b.get('product'), ['P1', 'P2', 'P3'], '产品层级'),
        'screening': {'cleared': boolfield(s.get('cleared'), '可执行范围'),
                      'redFlags': boolfield(s.get('redFlags'), '需优先核对信息'),
                      'notes': textfield(s.get('notes', ''), '筛查备注')},
        'isDemo': old.get('isDemo', False), 'createdAt': old.get('createdAt', now()),
        'updatedAt': now(), 'intakeStatus': 'pending',
    }
    if old and all(old.get(k) == obj[k] for k in ['side', 'route', 'product', 'screening']):
        obj['intakeStatus'] = old.get('intakeStatus', 'pending')
    return obj

def phase_input(value, label):
    if not isinstance(value, dict): raise ValueError(label + '记录未填写。')
    pain = value.get('pain')
    if isinstance(pain, bool) or not isinstance(pain, (int, float)) or not math.isfinite(pain) or not 0 <= pain <= 10:
        raise ValueError(label + '自评需为0至10的数字。')
    return {'pain': pain, 'swelling': choice(value.get('swelling'), ['none', 'same', 'increased'], label + '肿胀变化'),
            'note': textfield(value.get('note', ''), label + '备注', 1000)}

def save_profile(body, previous=None):
    obj = put('profiles', valid_profile(body, previous))
    if previous and any(previous.get(k) != obj[k] for k in ['side', 'route', 'product', 'screening']):
        for r in objects('records'):
            if r['profileId'] == obj['id']:
                r.update(updatedAt=now(), reviewStatus='pending')
                r['candidate'] = candidate(obj, r)
                put('records', r)
    return obj

def valid_record(body, previous=None):
    old = previous or {}
    b = {**old, **body}
    profile = get('profiles', b.get('profileId'))
    if profile['product'] != 'P2': raise ValueError('请使用产品2档案记录小腿提踵；产品1和产品3尚未开放该模块。')
    if old and b['profileId'] != old['profileId']: raise ValueError('不能更换已有训练记录的档案。')
    if b.get('product', 'P2') != 'P2' or b.get('module', 'calf-raise') != 'calf-raise':
        raise ValueError('当前视频与训练记录 Demo 范围是产品2小腿提踵能力。')
    date = textfield(b.get('date', ''), '训练日期', 10, True)
    try: dt.date.fromisoformat(date)
    except ValueError: raise ValueError('训练日期格式应为 YYYY-MM-DD。')
    obj = {'id': old.get('id', uid('record')), 'profileId': profile['id'], 'date': date,
           'product': 'P2', 'module': 'calf-raise', 'side': choice(b.get('side'), ['left', 'right'], '视频关注侧'),
           'note': textfield(b.get('note', ''), '训练备注'),
           'createdAt': old.get('createdAt', now()), 'updatedAt': now(), 'reviewStatus': 'pending'}
    for key in ['t0', 't1', 't2']:
        obj[key] = phase_input(b.get(key), key.upper())
    obj['t3'] = None if b.get('t3') is None else phase_input(b['t3'], '次日')
    obj['candidate'] = candidate(profile, obj)
    return obj

def save_review(body):
    profile = get('profiles', body.get('profileId'))
    record = get('records', body['recordId']) if body.get('recordId') else None
    if record and record['profileId'] != profile['id']: raise ValueError('训练记录与档案不匹配。')
    scope = choice(body.get('scope', 'record'), ['intake', 'record', 'stage'], '复核类型')
    options = {'intake': ['CONFIRM', 'DEFER'], 'record': ['ACKNOWLEDGED', 'NEEDS_INFO'], 'stage': ['PASS', 'HOLD', 'REGRESS', 'STOP']}
    decision = choice(body.get('decision'), options[scope], '人工决定')
    if scope != 'intake' and not record: raise ValueError('请选定作为复核依据的训练记录。')
    comment = textfield(body.get('comment', ''), '复核说明', 3000, True)
    confirm = boolfield(body.get('confirmIntake', False), '确认档案')
    if scope == 'stage' and decision == 'PASS' and record and record['t3'] is None:
        raise ValueError('次日反馈尚未补齐，请先补记录；可以先选择 HOLD 并保存复核意见。')
    if decision in ['PASS', 'CONFIRM'] and (profile['screening']['redFlags'] or not profile['screening']['cleared']):
        raise ValueError('筛查信息尚有待核对事项，请先确认可执行范围，再决定阶段。')
    if decision == 'PASS' and profile.get('intakeStatus') != 'confirmed' and not confirm:
        raise ValueError('请先人工确认档案，再保存阶段通过意见。')
    if decision == 'PASS' and any(a['recordId'] == record['id'] and a['status'] in ['queued', 'running'] for a in objects('analyses')):
        raise ValueError('视频仍在分析，请等结果完成后再进行阶段复核。')
    if confirm and (profile['screening']['redFlags'] or not profile['screening']['cleared']) and decision not in ['STOP', 'DEFER']:
        raise ValueError('筛查信息仍需核对，请先更新档案，或记录暂缓处理。')
    obj = {'id': uid('review'), 'profileId': profile['id'], 'recordId': record['id'] if record else None,
           'scope': scope, 'stageLabel': 'P2 · 模块3 · 小腿提踵能力' if scope == 'stage' else None,
           'decision': decision, 'comment': comment, 'reviewer': 'Dee', 'confirmIntake': confirm,
           'recordUpdatedAt': record.get('updatedAt') if record else None, 'createdAt': now()}
    if confirm or scope == 'intake' or decision == 'STOP':
        profile['intakeStatus'] = 'deferred' if decision in ['STOP', 'DEFER'] else 'confirmed'
        profile['updatedAt'] = now()
        put('profiles', profile)
        if profile['intakeStatus'] == 'deferred':
            for related in objects('records'):
                if related['profileId'] == profile['id']:
                    related.update(updatedAt=now(), reviewStatus='pending')
                    put('records', related)
            if record:
                record = get('records', record['id'])
                obj['recordUpdatedAt'] = record['updatedAt']
    if record and scope != 'intake':
        record['reviewStatus'] = 'pending' if decision == 'NEEDS_INFO' else 'reviewed'
        record['candidate'] = candidate(profile, record)
        put('records', record)
    put('reviews', obj)
    return obj

def seed():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'analyses').mkdir(exist_ok=True)
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,body TEXT,created TEXT,PRIMARY KEY(kind,id))')
    if not objects('profiles'):
        profile = {'id': 'demo-profile', 'name': '小林 · 示例档案', 'side': 'left', 'route': 'conservative',
                   'goal': '记录基础活动反馈，逐步看清运动能力变化', 'product': 'P2',
                   'screening': {'cleared': True, 'redFlags': False, 'notes': '模拟资料：用于演示流程，不代表真实学员或专业许可。'},
                   'isDemo': True, 'createdAt': now(), 'updatedAt': now(), 'intakeStatus': 'pending'}
        put('profiles', profile)
        record = valid_record({'profileId': profile['id'], 'date': dt.date.today().isoformat(), 'side': 'left',
                               't0': {'pain': 1, 'swelling': 'none', 'note': '示例：训练前状态记录'},
                               't1': {'pain': 1, 'swelling': 'same', 'note': '示例：记录过程中感受'},
                               't2': {'pain': 2, 'swelling': 'same', 'note': '示例：较训练前增加，交由人工复核'},
                               't3': None, 'note': '模拟训练记录；不是训练处方。'})
        record['id'] = 'demo-record'
        put('records', record)
    for a in objects('analyses'):
        if a['status'] in ['queued', 'running']:
            a.update(status='failed', reason='上次运行已中断，请重新提交视频。')
            put('analyses', a)

def all_state():
    profiles = objects('profiles')
    profile_map = {p['id']: p for p in profiles}
    records = objects('records')
    for r in records:
        if r['profileId'] in profile_map: r['candidate'] = candidate(profile_map[r['profileId']], r)
    return {'profiles': profiles, 'records': records, 'reviews': objects('reviews'),
            'analyses': [analysis_status(a['id']) for a in objects('analyses')],
            'meta': {'version': VERSION, 'engineAvailable': PYTHON.exists() and ENGINE.exists(), 'engineBusy': BUSY}}

def report(profile_id):
    state = all_state()
    p = get('profiles', profile_id)
    records = [r for r in state['records'] if r['profileId'] == profile_id]
    ids = {r['id'] for r in records}
    reviews = [r for r in state['reviews'] if r['profileId'] == profile_id]
    analyses = [a for a in state['analyses'] if a['recordId'] in ids]
    return {'profile': p, 'records': records, 'reviews': reviews, 'analyses': analyses,
            'summary': {'recordCount': len(records), 'reviewCount': len(reviews),
                        'pendingNextDay': sum(r['t3'] is None for r in records),
                        'pendingReview': sum(r['reviewStatus'] != 'reviewed' for r in records),
                        'latestDecision': next((v['decision'] for v in reversed(reviews) if v.get('scope') == 'stage' and
                                                (v['decision'] != 'PASS' or p['intakeStatus'] == 'confirmed') and
                                                any(r['id'] == v['recordId'] and r['updatedAt'] == v.get('recordUpdatedAt') for r in records) and
                                                not any(r['createdAt'] > v['createdAt'] for r in records)), None)},
            'generatedAt': now(), 'notice': '这是结构化记录与人工复核摘要；不自动证明疗效或重返运动资格。'}

def analysis_status(ident):
    a = get('analyses', ident)
    if a['status'] == 'running':
        try:
            progress = json.loads((DATA / 'analyses' / ident / 'progress.json').read_text())
            a['progress'] = max(0, min(99, int(progress.get('progress', 0))))
            a['message'] = str(progress.get('message', progress.get('reason', '正在本机分析视频')))[:300]
        except (ValueError, OSError, TypeError): pass
    return a

def refresh_record(ident):
    r = get('records', ident)
    r.update(updatedAt=now(), reviewStatus='pending')
    put('records', r)

def run_analysis(ident, source, output, side):
    global BUSY
    a = get('analyses', ident)
    try:
        a.update(status='running', progress=1)
        put('analyses', a)
        env = dict(os.environ, MPLCONFIGDIR=str(DATA / '.matplotlib'), OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')
        with (output / 'engine.log').open('w') as log:
            process = subprocess.run([str(PYTHON), str(ENGINE), '--input', str(source), '--output', str(output), '--side', side],
                                     stdout=log, stderr=subprocess.STDOUT, env=env, timeout=480, cwd=ROOT)
        if process.returncode:
            message = '视频分析未完成，请检查视频格式、时长与拍摄条件后重试。'
            if (output / 'error.json').exists():
                error = json.loads((output / 'error.json').read_text())
                message = str(error.get('error', message))[:500]
            elif (output / 'progress.json').exists():
                error = json.loads((output / 'progress.json').read_text())
                message = str(error.get('reason', message))[:500]
            raise ValueError(message)
        result = json.loads((output / 'result.json').read_text())
        result['mode'] = 'real_pose'
        for key in ['overlayVideo', 'poster']:
            if result.get(key):
                filename = Path(result[key]).name
                result[key] = '/media/' + ident + '/' + filename if (output / filename).is_file() else None
        a.update(status='completed', progress=100, result=result)
        put('analyses', a)
        refresh_record(a['recordId'])
    except subprocess.TimeoutExpired:
        a.update(status='failed', reason='本机分析超过8分钟，已停止。请使用更短、清晰的视频。')
        put('analyses', a)
    except Exception as e:
        a.update(status='failed', reason=str(e)[:500] if isinstance(e, ValueError) else '分析发生异常，请重试或查看本机日志。')
        put('analyses', a)
    finally:
        with LOCK: BUSY = False

def simulated_analysis(record_id, side):
    record = get('records', record_id)
    if side != record['side']: raise ValueError('分析侧别与训练记录不一致，请先修改记录或选择对应侧。')
    # Synthetic observations pass through the same post-processing as real video.
    # They never invoke or claim human pose inference.
    from engine.motion import summarize
    observations = []
    for i in range(121):
        t = i / 8
        phase = t % 3
        if phase < .5 or phase >= 2.25: lift = 0
        elif phase < 1.25: lift = .34 * (phase - .5) / .75
        elif phase < 1.5: lift = .34
        else: lift = .34 * (2.25 - phase) / .75
        observations.append({'t': t, 'heelLift': lift, 'confidence': 1, 'valid': True,
                             'people': 1, 'toeX': 300, 'toeY': 400, 'footLength': 100, 'reason': ''})
    result, _ = summarize(observations, 15, 8, side)
    result.update(engine='模拟关键点 · 共用计数逻辑', mode='simulated_keypoints',
                  sourceLabel='模拟关键点样例 · 非人体视频识别',
                  warnings=['这是人工构造的关键点曲线，不是人体视频识别结果。',
                            '曲线通过与真实视频相同的周期计数逻辑；不能据此推断真人识别准确率。'],
                  modelInfo={'source': 'synthetic_signal', 'clinicalValidation': False,
                             'ruleVersion': 'heel-candidate-0.1'})
    a = {'id': uid('analysis'), 'recordId': record_id, 'side': side, 'status': 'completed', 'progress': 100,
         'mode': 'simulated_keypoints', 'createdAt': now(), 'result': result}
    put('analyses', a)
    refresh_record(record_id)
    return a

class Handler(BaseHTTPRequestHandler):
    server_version = 'DeeAnkle/0.1'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        print('%s %s' % (self.log_date_time_string(), fmt % args), flush=True)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        super().end_headers()

    def json_response(self, obj, status=200, download=None):
        data = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        if download: self.send_header('Content-Disposition', 'attachment; filename="ankle-stage-record.json"')
        self.end_headers()
        self.wfile.write(data)

    def valid_origin(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        expected = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        if host not in expected or (origin and origin not in {'http://' + h for h in expected}):
            raise PermissionError('此演示仅供本机访问，请从本机启动入口打开。')

    def read_json(self):
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size <= 100_000: raise ValueError('请求数据大小不正确。')
        if 'application/json' not in self.headers.get('Content-Type', ''): raise ValueError('请使用JSON格式提交。')
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict): raise ValueError('请求应为JSON对象。')
        return data

    def do_GET(self):
        try:
            self.valid_origin()
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            if path == '/api/health':
                return self.json_response({'ok': True, 'service': 'dee-ankle-rehab', 'version': VERSION,
                                           'engineAvailable': PYTHON.exists() and ENGINE.exists(), 'engineBusy': BUSY})
            if path == '/api/state': return self.json_response(all_state())
            if path.startswith('/api/analyses/'):
                return self.json_response(analysis_status(path.rsplit('/', 1)[-1]))
            if path in ['/api/report', '/api/export']:
                return self.json_response(report(query.get('profileId', [''])[0]), download=path.endswith('export'))
            if path.startswith('/api/'): return self.json_response({'error': '接口不存在。'}, 404)
            if path.startswith('/media/'):
                pieces = path.strip('/').split('/')
                if len(pieces) != 3 or not re.fullmatch(r'analysis-[a-f0-9]{16}', pieces[1]):
                    return self.json_response({'error': '文件路径无效。'}, 404)
                filename = pieces[2]
                if filename not in ['overlay.mp4', 'poster.jpg', 'source.mp4', 'source.mov', 'source.webm', 'source.avi', 'source.m4v']:
                    return self.json_response({'error': '文件不可访问。'}, 404)
                return self.serve_file(DATA / 'analyses' / pieces[1] / filename)
            relative = path.lstrip('/') or 'index.html'
            target = (DIST / relative).resolve()
            if not target.is_relative_to(DIST.resolve()): return self.json_response({'error': '路径无效。'}, 404)
            return self.serve_file(target)
        except PermissionError as e: self.json_response({'error': str(e)}, 403)
        except (ValueError, TypeError, KeyError) as e: self.json_response({'error': str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception:
            self.json_response({'error': '本机服务出现异常，请刷新或重新启动。'}, 500)

    def serve_file(self, path):
        if not path.is_file(): return self.json_response({'error': '文件不存在。'}, 404)
        length = path.stat().st_size
        start, end = 0, length - 1
        range_header = self.headers.get('Range')
        status = 200
        if range_header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
            if not match or not any(match.groups()):
                self.send_response(416); self.send_header('Content-Length', '0'); self.end_headers(); return
            a, b = match.groups()
            if a: start, end = int(a), min(int(b) if b else end, end)
            else: start = max(0, length - int(b))
            if start > end or start >= length:
                self.send_response(416); self.send_header('Content-Range', 'bytes */' + str(length)); self.send_header('Content-Length', '0'); self.end_headers(); return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{length}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk: break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):
        try:
            self.valid_origin()
            parsed = urlparse(self.path)
            path = parsed.path
            if path == '/api/analyses': return self.upload(parse_qs(parsed.query))
            body = self.read_json()
            if path == '/api/profiles': return self.json_response(save_profile(body), 201)
            if path.startswith('/api/profiles/'):
                p = get('profiles', path.rsplit('/', 1)[-1])
                return self.json_response(save_profile(body, p))
            if path == '/api/records': return self.json_response(put('records', valid_record(body)), 201)
            if path.startswith('/api/records/'):
                r = get('records', path.rsplit('/', 1)[-1])
                return self.json_response(put('records', valid_record(body, r)))
            if path == '/api/reviews': return self.json_response(save_review(body), 201)
            if path == '/api/demo-analysis':
                side = choice(body.get('side', 'left'), ['left', 'right'], '关注侧')
                return self.json_response(simulated_analysis(body.get('recordId'), side), 201)
            return self.json_response({'error': '接口不存在。'}, 404)
        except PermissionError as e:
            self.close_connection = True; self.json_response({'error': str(e)}, 403)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            self.close_connection = True; self.json_response({'error': str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception:
            self.close_connection = True; self.json_response({'error': '保存失败，请重试。'}, 500)

    def upload(self, query):
        global BUSY
        if not PYTHON.exists() or not ENGINE.exists():
            raise ValueError('动作识别环境尚未就绪。')
        record_id = query.get('recordId', [''])[0]
        record = get('records', record_id)
        side = choice(query.get('side', ['left'])[0], ['left', 'right'], '关注侧')
        if side != record['side']: raise ValueError('分析侧别与训练记录不一致，请选择对应侧或先修改记录。')
        filename = query.get('filename', ['video.mp4'])[0]
        extension = Path(filename).suffix.lower()
        if extension not in ['.mp4', '.mov', '.avi', '.webm', '.m4v']:
            raise ValueError('请上传 MP4、MOV、AVI 或 WebM 视频。')
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size <= MAX_UPLOAD: raise ValueError('视频大小需在80MB以内。')
        with LOCK:
            if BUSY:
                self.close_connection = True
                return self.json_response({'error': '已有视频正在分析，请等本次完成再提交。'}, 409)
            BUSY = True
        try:
            ident = uid('analysis')
            output = DATA / 'analyses' / ident
            output.mkdir()
            source = output / ('source' + extension)
            self.connection.settimeout(60)
            left = size
            with source.open('wb') as f:
                while left:
                    data = self.rfile.read(min(left, 1024 * 1024))
                    if not data: raise ValueError('视频上传中断，请重新提交。')
                    f.write(data)
                    left -= len(data)
            self.connection.settimeout(30)
            a = {'id': ident, 'recordId': record_id, 'side': side, 'status': 'queued', 'progress': 0,
                 'mode': 'real_pose', 'createdAt': now()}
            put('analyses', a)
            refresh_record(record_id)
            thread = threading.Thread(target=run_analysis, args=(ident, source, output, side), daemon=True)
            thread.start()
            self.json_response(a, 202)
        except Exception:
            with LOCK: BUSY = False
            raise

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8843)
    args = parser.parse_args()
    seed()
    httpd = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Dee ankle rehab: http://127.0.0.1:{args.port} (local only)', flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally: httpd.server_close()

if __name__ == '__main__': main()
