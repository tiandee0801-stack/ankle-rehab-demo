#!/usr/bin/env python3
"""Bounded local video inference using the existing, verified MMPose venv."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from motion import observation, summarize, SIDE_POINTS

ROOT = Path(os.environ.get('ANKLE_MMPOSE_ROOT', str(Path.home() / 'Documents/运动健身资料/mmpose-main')))
FFMPEG = Path(os.environ.get('ANKLE_FFMPEG', shutil.which('ffmpeg') or str(Path.home() / 'Documents/运动健身资料/openpose-master/.native/bin/ffmpeg')))
FFPROBE = Path(os.environ.get('ANKLE_FFPROBE', str(FFMPEG.with_name('ffprobe'))))
MAX_BYTES = 80 * 1024 * 1024
TARGET_FPS = 8
MAX_FRAMES = 240


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
    temp.replace(path)


def progress(out, value, status='running', reason=None):
    data = {'progress': value, 'status': status,
            'updatedAt': datetime.now(timezone.utc).isoformat()}
    if reason:
        data['reason'] = reason
    atomic_json(out / 'progress.json', data)


def inspect_video(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('未找到可读取的视频文件。')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('视频超过80MB，请先裁剪或压缩。')
    probe = subprocess.run([str(FFPROBE), '-v', 'error', '-protocol_whitelist', 'file,pipe', '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height,avg_frame_rate,duration:format=duration',
                            '-of', 'json', str(path)], capture_output=True, text=True, timeout=20)
    if probe.returncode:
        raise ValueError('无法解析视频，请上传常见MP4、MOV或AVI视频。')
    meta = json.loads(probe.stdout)
    if not meta.get('streams'):
        raise ValueError('文件中没有视频画面。')
    stream = meta['streams'][0]
    candidates = [stream.get('duration'), meta.get('format', {}).get('duration')]
    durations = []
    for value in candidates:
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                durations.append(value)
        except (ValueError, TypeError):
            pass
    if not durations:
        raise ValueError('无法确认视频时长，请重新导出视频。')
    duration = max(durations)
    if duration > 30.001:
        raise ValueError('视频超过30秒，请截取较短片段后重试。')
    width, height = int(stream.get('width', 0)), int(stream.get('height', 0))
    if min(width, height) < 120 or max(width, height) > 8192:
        raise ValueError('视频分辨率不适合分析，请上传清晰且不超过8K的录像。')
    return duration, stream


def run(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'observations.json', 'overlay.mp4', 'poster.jpg'):
        (out / name).unlink(missing_ok=True)
    progress(out, 1)
    duration, metadata = inspect_video(args.input)
    start = time.perf_counter()
    frames = out / '_frames'
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(exist_ok=True)
    # Decode with a strict wall-clock, output-frame, spatial and file-count bound.
    command = [str(FFMPEG), '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(args.input.resolve()),
               '-t', '30', '-an', '-vf',
               'fps=8,scale=1280:1280:force_original_aspect_ratio=decrease',
               '-frames:v', str(MAX_FRAMES), '-q:v', '3', str(frames / '%04d.jpg')]
    decoded = subprocess.run(command, capture_output=True, timeout=90)
    if decoded.returncode:
        raise ValueError('视频解码失败，请重新导出为MP4后重试。')
    paths = sorted(frames.glob('*.jpg'))
    if not paths:
        raise ValueError('未能读取有效视频帧。')
    progress(out, 5)
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'deployment/.matplotlib'))
    sys.path.insert(0, str(ROOT))
    import cv2
    import numpy as np
    import torch
    from mmdet.apis import init_detector, inference_detector
    from mmpose.apis import init_model, inference_topdown
    from mmpose.utils import adapt_mmdet_pipeline, register_all_modules

    torch.set_num_threads(4)
    det_config = ROOT / 'projects/rtmpose/rtmdet/person/rtmdet_nano_320-8xb32_coco-person.py'
    det_weights = ROOT / 'deployment/models/rtmdet-nano-person.pth'
    pose_config = ROOT / 'configs/wholebody_2d_keypoint/rtmpose/coco-wholebody/rtmpose-m_8xb64-270e_coco-wholebody-256x192.py'
    pose_weights = ROOT / 'deployment/models/rtmpose-m-wholebody.pth'
    detector = init_detector(str(det_config), str(det_weights), device='cpu')
    detector.cfg = adapt_mmdet_pipeline(detector.cfg)
    register_all_modules()
    pose = init_model(str(pose_config), str(pose_weights), device='cpu')
    progress(out, 12)
    observations = []
    points_for_drawing = []
    for index, path in enumerate(paths):
        if time.perf_counter() - start > 300:
            raise ValueError('分析用时过长，已停止；请上传更短片段。')
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('视频帧损坏，请重新导出视频。')
        height, width = image.shape[:2]
        with torch.inference_mode():
            det = inference_detector(detector, image).pred_instances.cpu().numpy()
        keep = np.flatnonzero((det.labels == 0) & (det.scores >= .5))
        points = scores = None
        if len(keep) == 1:
            with torch.inference_mode():
                predictions = inference_topdown(pose, image, bboxes=det.bboxes[keep], bbox_format='xyxy')
            if predictions:
                points = predictions[0].pred_instances.keypoints[0]
                scores = predictions[0].pred_instances.keypoint_scores[0]
        sample = observation(index / TARGET_FPS, points, scores, args.side,
                             width, height, people=len(keep),
                             detector_confidence=float(det.scores[keep[0]]) if len(keep) == 1 else 0)
        observations.append(sample)
        points_for_drawing.append((points, scores))
        progress(out, 12 + int(73 * (index + 1) / len(paths)))
    result, filtered = summarize(observations, duration, TARGET_FPS, args.side)
    # Save only minimal keypoints for audit; never include a user's absolute path.
    evidence = [{**s, 'keypoints': None if points is None else
                 {str(i): [float(points[i][0]), float(points[i][1]), float(scores[i])]
                  for i in SIDE_POINTS[args.side]}}
                for s, (points, scores) in zip(filtered, points_for_drawing)]
    atomic_json(out / 'observations.json', evidence)
    poster_index = next((i for i, sample in enumerate(filtered) if sample['valid']), None)
    if poster_index is None:
        poster_index = next((i for i, (points, _) in enumerate(points_for_drawing)
                             if points is not None), 0)
    for index, (path, sample, point_data) in enumerate(zip(paths, filtered, points_for_drawing)):
        image = cv2.imread(str(path))
        points, scores = point_data
        if points is not None:
            ids = SIDE_POINTS[args.side]
            color = (90, 210, 80) if sample['valid'] else (30, 140, 240)
            for a, b in [(ids[0], ids[1]), (ids[1], ids[4]), (ids[4], ids[2])]:
                if min(scores[a], scores[b]) >= .45:
                    cv2.line(image, tuple(np.rint(points[a]).astype(int)),
                             tuple(np.rint(points[b]).astype(int)), color, 3)
            for i in ids:
                if scores[i] >= .45:
                    cv2.circle(image, tuple(np.rint(points[i]).astype(int)), 4, color, -1)
        cv2.rectangle(image, (0, 0), (image.shape[1], 65), (24, 34, 40), -1)
        status = 'OBSERVABLE' if sample['valid'] else 'REVIEW REQUIRED'
        cv2.putText(image, f'LOCAL MODEL | {args.side.upper()} | {status}', (12, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, .53, (230, 235, 240), 1)
        cv2.putText(image, f'{sample["t"]:.2f}s | Image geometry, not clinical ROM', (12, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, .48, (230, 235, 240), 1)
        cv2.imwrite(str(path), image)
        if index == poster_index:
            cv2.imwrite(str(out / 'poster.jpg'), image)
    progress(out, 90)
    encode = subprocess.run([str(FFMPEG), '-v', 'error', '-nostdin', '-y',
                             '-framerate', str(TARGET_FPS), '-i', str(frames / '%04d.jpg'),
                             '-an', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                             '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                             '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out / 'overlay.mp4')],
                            capture_output=True, timeout=90)
    result['poster'] = 'poster.jpg'
    if encode.returncode == 0 and (out / 'overlay.mp4').stat().st_size > 0:
        result['overlayVideo'] = 'overlay.mp4'
    else:
        result['warnings'].append('标注视频导出失败，轨迹与静态预览仍可查看。')
    result['modelInfo'] = {
        'pose': 'RTMPose-M COCO-WholeBody 133', 'detector': 'RTMDet-nano person',
        'device': 'cpu', 'poseSha256': hashlib.sha256(pose_weights.read_bytes()).hexdigest(),
        'detectorSha256': hashlib.sha256(det_weights.read_bytes()).hexdigest(),
        'mmposeVersion': __import__('mmpose').__version__,
        'inputSha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'inputWidth': metadata['width'], 'inputHeight': metadata['height'],
        'elapsedSeconds': round(time.perf_counter() - start, 3),
        'sampling': '8 fps offline; maximum 1280px; not real-time measurement',
        'ruleVersion': 'heel-candidate-0.1', 'clinicalValidation': False,
    }
    atomic_json(out / 'result.json', result)
    shutil.rmtree(frames, ignore_errors=True)
    progress(out, 100, 'completed')
    print(f'完成：{len(paths)}帧，质量 {result["quality"]}，候选次数 {result["repCount"]}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='本地足部动作观察，不作医学判断')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--side', choices=['left', 'right'], required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        run(args)
        return 0
    except Exception as error:
        # Detailed traceback is intentionally not returned to the UI or logs.
        reason = str(error) if isinstance(error, ValueError) else '本地分析失败，请检查引擎环境或重新导出较短的视频。'
        progress(args.output, 0, 'failed', reason)
        shutil.rmtree(args.output / '_frames', ignore_errors=True)
        print(reason, file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
