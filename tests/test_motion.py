"""Synthetic geometry tests: these are not clinical or model accuracy tests."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from motion import observation, summarize


def pose(t, lift=0.0, dx=0.0, confidence=.95, people=1):
    points = [[400., 300.] for _ in range(133)]
    scores = [confidence] * 133
    points[13], points[15] = [350 + dx, 280], [350 + dx, 400]
    points[17], points[18] = [400 + dx, 430], [397 + dx, 431]
    points[19] = [350 + dx, 430 - lift * 50]
    return observation(t, points, scores, width=800, height=600, people=people)


def signal(t):
    # 1-second neutral start; 2-second full up/down cycles; flat gaps.
    if t < 1:
        return 0
    phase = (t - 1) % 3
    return .50 * math.sin(math.pi * phase / 2) if phase < 2 else 0


class MotionTests(unittest.TestCase):
    def result(self, samples):
        return summarize(samples, len(samples) / 8, 8, 'left')[0]

    def test_two_complete_cycles(self):
        result = self.result([pose(i / 8, signal(i / 8)) for i in range(56)])
        self.assertEqual(result['quality'], 'usable')
        self.assertEqual(result['repCount'], 2)
        self.assertEqual(len(result['events']), 2)

    def test_stationary_zero(self):
        result = self.result([pose(i / 8) for i in range(32)])
        self.assertEqual(result['repCount'], 0)
        self.assertEqual(result['tempoSeconds'], None)

    def test_no_cycle_across_occlusion(self):
        samples = [pose(i / 8, signal(i / 8)) for i in range(32)]
        samples[17] = pose(17 / 8, .5, confidence=.1)
        result = self.result(samples)
        self.assertEqual(result['repCount'], 0)
        self.assertTrue(result['reviewSegments'])

    def test_walking_drift_does_not_count(self):
        samples = [pose(i / 8, signal(i / 8), dx=i * 2) for i in range(56)]
        result = self.result(samples)
        self.assertIsNone(result['repCount'])
        self.assertLess(result['coverage'], .4)

    def test_camera_translation_alone_does_not_create_cycles(self):
        result = self.result([pose(i / 8, dx=2 * math.sin(i / 3)) for i in range(40)])
        self.assertEqual(result['repCount'], 0)

    def test_multiple_people_global_rejection(self):
        samples = [pose(i / 8, signal(i / 8)) for i in range(56)]
        samples[20] = pose(20 / 8, people=2)
        result = self.result(samples)
        self.assertIsNone(result['repCount'])
        self.assertNotEqual(result['quality'], 'usable')

    def test_low_confidence_has_no_numeric_lift(self):
        result = self.result([pose(i / 8, confidence=.2) for i in range(32)])
        self.assertEqual(result['quality'], 'unusable')
        self.assertIsNone(result['repCount'])
        self.assertTrue(all(s['heelLift'] is None for s in result['series']))

    def test_incomplete_cycle_not_counted(self):
        result = self.result([pose(i / 8, 0 if i < 8 else .5) for i in range(32)])
        self.assertEqual(result['repCount'], 0)

    def test_tiny_foot_rejected(self):
        points = [[400., 300.] for _ in range(133)]
        points[13], points[15], points[17], points[18], points[19] = [300, 100], [300, 300], [305, 310], [304, 311], [300, 310]
        s = observation(0, points, [.95] * 133, width=800, height=600)
        self.assertFalse(s['valid'])


if __name__ == '__main__':
    unittest.main()
