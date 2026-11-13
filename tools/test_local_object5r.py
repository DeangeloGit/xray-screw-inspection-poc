"""Geometry and decision-boundary checks; not a DINO accuracy evaluation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'experiments/dino')]
from local_object5r import compact_cores, review_lost_keep


class LocalObjectTests(unittest.TestCase):
    def image(self):
        image = np.ones((140, 100), np.float32)
        cv2.line(image, (50, 15), (50, 120), .2, 2)
        cv2.circle(image, (50, 80), 8, .05, -1)
        return image

    def test_detaches_compact_object_from_thin_wire(self):
        image = self.image()
        cores = compact_cores(image, [40, 10, 21, 115])
        self.assertEqual(len(cores), 1)
        x, y, w, h = cores[0]['box']
        self.assertTrue(x <= 50 < x+w and y <= 80 < y+h)
        self.assertLess(h, 30)
        shifted = compact_cores(np.roll(image, 10, axis=0), [40, 20, 21, 115])[0]['box']
        self.assertEqual(shifted, [x, y+10, w, h])

    def test_uniform_and_wire_only_do_not_create_core(self):
        image = np.ones((140, 100), np.float32)
        self.assertEqual(compact_cores(image, [40, 10, 21, 115]), [])
        cv2.line(image, (50, 15), (50, 120), .2, 2)
        self.assertEqual(compact_cores(image, [40, 10, 21, 115]), [])

    def test_no_new_alarm_without_baseline_keep(self):
        excluded = dict(filter_recommendation='exclude')
        with patch('dino_paired_optimized.classify_candidate') as classifier:
            self.assertIs(review_lost_keep(None, None, None, excluded, excluded), excluded)
            classifier.assert_not_called()

    def test_paired_exclusion_remains_excluded(self):
        baseline = dict(filter_recommendation='keep')
        trial = dict(filter_recommendation='exclude', canonical_object=dict(box=[40, 10, 21, 115]))
        with patch('dino_paired_optimized.classify_candidate', return_value=dict(filter_recommendation='exclude')):
            result = review_lost_keep(None, np.ones((140,100), np.float32), self.image(), baseline, trial)
        self.assertEqual(result['filter_recommendation'], 'exclude')
        self.assertFalse(result['local_object5r']['accepted'])
        self.assertNotIn('local_object5r', trial)


if __name__ == '__main__':
    unittest.main()
