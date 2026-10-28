"""Meaningful business-state regressions; isolated temp DB, no user changes."""
import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ['ANKLE_DATA_DIR'] = TEMP.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SPEC = importlib.util.spec_from_file_location('ankle_server', Path(__file__).resolve().parents[1] / 'server.py')
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)

class BusinessTests(unittest.TestCase):
    def setUp(self):
        s.seed()
        with s.connect() as db: db.execute('DELETE FROM objects')
        self.p = s.save_profile({'name':'测试档案','side':'left','route':'conservative','goal':'流程验证','product':'P2',
            'screening':{'cleared':True,'redFlags':False,'notes':''}})
        self.r = s.put('records', s.valid_record({'profileId':self.p['id'],'date':'2026-10-27','side':'left',
            't0':{'pain':1,'swelling':'none'},'t1':{'pain':1,'swelling':'same'},'t2':{'pain':1,'swelling':'same'}}))

    def confirm(self):
        return s.save_review({'scope':'intake','decision':'CONFIRM','profileId':self.p['id'],'comment':'人工确认示例档案'})

    def next_day(self):
        self.r = s.put('records',s.valid_record({'t3':{'pain':1,'swelling':'same'}}, self.r))

    def review(self, decision='HOLD', scope='stage'):
        return s.save_review({'scope':scope,'profileId':self.p['id'],'recordId':self.r['id'],'decision':decision,'comment':'人工复核测试'})

    def test_missing_next_day_never_passes(self):
        self.confirm()
        self.assertTrue(self.r['candidate']['missingNextDay'])
        with self.assertRaisesRegex(ValueError,'次日'): self.review('PASS')

    def test_record_review_does_not_set_stage(self):
        self.review('ACKNOWLEDGED','record')
        self.assertIsNone(s.report(self.p['id'])['summary']['latestDecision'])
        with self.assertRaises(ValueError): self.review('PASS','record')

    def test_explicit_intake_required(self):
        self.next_day()
        with self.assertRaisesRegex(ValueError,'确认档案'): self.review('PASS')
        self.confirm()
        self.review('PASS')
        self.assertEqual(s.report(self.p['id'])['summary']['latestDecision'],'PASS')

    def test_record_change_invalidates_review_and_retains_history(self):
        self.confirm(); self.next_day(); self.review('PASS')
        changed = s.put('records',s.valid_record({'t3':{'pain':3,'swelling':'increased'}},self.r))
        self.assertEqual(changed['reviewStatus'],'pending')
        report=s.report(self.p['id'])
        self.assertIsNone(report['summary']['latestDecision'])
        self.assertEqual(len(report['reviews']),2)

    def test_screening_change_invalidates_stage(self):
        self.confirm(); self.next_day(); self.review('PASS')
        p=s.get('profiles',self.p['id'])
        s.save_profile({'screening':{'cleared':False,'redFlags':True,'notes':'状态有变化'}},p)
        report=s.report(self.p['id'])
        self.assertIsNone(report['summary']['latestDecision'])
        self.assertEqual(report['records'][0]['candidate']['priority'],'Attention')
        with self.assertRaises(ValueError): self.confirm()

    def test_needs_info_stays_pending(self):
        self.review('NEEDS_INFO','record')
        self.assertEqual(s.get('records',self.r['id'])['reviewStatus'],'pending')

    def test_invalid_pain_and_missing_inputs_rejected(self):
        for v in [-1,11,float('nan'),True,'1']:
            with self.assertRaises(ValueError): s.valid_record({'t2':{'pain':v,'swelling':'same'}},self.r)
        with self.assertRaises(ValueError): s.valid_record({'t1':None},self.r)

    def test_profile_and_record_cannot_cross(self):
        p2=s.save_profile({'name':'其他人','side':'right','route':'unsure','goal':'测试','product':'P2',
            'screening':{'cleared':False,'redFlags':False,'notes':''}})
        with self.assertRaises(ValueError): s.save_review({'profileId':p2['id'],'recordId':self.r['id'],'scope':'record','decision':'ACKNOWLEDGED','comment':'错误关联'})

    def test_p1_cannot_create_p2_module(self):
        s.save_profile({'product':'P1'},self.p)
        with self.assertRaises(ValueError): s.valid_record({},self.r)

    def test_simulation_marked_and_resets_review(self):
        self.review('ACKNOWLEDGED','record')
        a=s.simulated_analysis(self.r['id'],'left')
        self.assertEqual(a['mode'],'simulated_keypoints')
        self.assertEqual(a['result']['modelInfo']['clinicalValidation'],False)
        self.assertEqual(s.get('records',self.r['id'])['reviewStatus'],'pending')

    def test_review_comment_required(self):
        with self.assertRaises(ValueError): s.save_review({'scope':'intake','decision':'CONFIRM','profileId':self.p['id'],'comment':''})

    def test_stop_defers_without_checkbox(self):
        self.confirm(); self.next_day(); self.review('PASS')
        self.review('STOP')
        self.assertEqual(s.get('profiles',self.p['id'])['intakeStatus'],'deferred')
        self.assertEqual(s.report(self.p['id'])['summary']['latestDecision'],'STOP')

    def test_intake_defer_invalidates_old_pass(self):
        self.confirm(); self.next_day(); self.review('PASS')
        s.save_review({'scope':'intake','decision':'DEFER','profileId':self.p['id'],'comment':'等待核对'})
        report=s.report(self.p['id'])
        self.assertIsNone(report['summary']['latestDecision'])
        self.assertEqual(report['records'][0]['reviewStatus'],'pending')

    def test_analysis_side_must_match_record(self):
        with self.assertRaisesRegex(ValueError,'侧别'): s.simulated_analysis(self.r['id'],'right')

if __name__ == '__main__': unittest.main()
