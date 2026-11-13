"""Synthetic contract tests only; no private DINO accuracy claims."""
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'experiments/dino')]
from live5r_review import ReviewBundle, feature_sha, sha


@dataclass
class FakeSnapshot:
    manifest: dict
    feature_bank: object
    identity: str = 'synthetic-only'


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bank = np.ones((142, 8, 2, 384), np.float32)
        self.base = FakeSnapshot(dict(sha256='synthetic-model', model_id='synthetic', example_bank={
            'screw': dict(ids=[f'S{i}' for i in range(52)]),
            'normal': dict(ids=[f'N{i}' for i in range(90)])}), self.bank)
        np.savez(self.root/'additions.npz', positive=np.full((3,8,2,384), 2, np.float32),
                 normal=np.full((6,8,2,384), 3, np.float32),
                 positive_ids=np.array(['P0','P1','P2']), normal_ids=np.array([f'Q{i}' for i in range(6)]))
        np.savez(self.root/'visible-part.npz', bank=np.ones((133,8,2,384), np.float32))
        self.meta = dict(schema_version=1, model_sha256='synthetic-model', base_feature_sha256=feature_sha(self.bank),
                         part_screw=50, part_normal=83, qualification=dict(status='passed'),
                         files={n:sha(self.root/n) for n in ['additions.npz','visible-part.npz']},
                         policies={n:sha(ROOT/'experiments/dino'/n) for n in ['local_object5r.py','alarm_review5r.py','live5r_review.py']})
        self.save_meta()

    def save_meta(self):
        (self.root/'manifest.json').write_text(json.dumps(self.meta), encoding='utf-8')

    def test_pending_bundle_cannot_start_live(self):
        self.meta['qualification']['status'] = 'pending'
        self.save_meta()
        with self.assertRaises(ValueError):
            ReviewBundle(self.root)

    def test_feature_corruption_is_rejected(self):
        with (self.root/'additions.npz').open('ab') as stream:
            stream.write(b'corrupted')
        with self.assertRaises(ValueError):
            ReviewBundle(self.root)

    def test_additions_preserve_current_bank_and_change_cache_identity(self):
        bundle = ReviewBundle(self.root)
        before = copy.deepcopy(self.base.manifest)
        trial = bundle.trial_snapshot(self.base)
        self.assertEqual(trial.feature_bank.shape[0], 151)
        self.assertTrue(np.array_equal(trial.feature_bank[:52], self.bank[:52]))
        self.assertTrue(np.array_equal(trial.feature_bank[55:145], self.bank[52:]))
        self.assertEqual(self.base.manifest, before)
        self.assertNotEqual(bundle.tagged_snapshot(self.base).identity, self.base.identity)
        self.assertEqual(bundle.tagged_snapshot(self.base).identity, bundle.tagged_snapshot(self.base).identity)
        self.assertTrue(bundle.details(self.base)['base_bank_matches_validation'])

    def test_counts_overlays_and_original_exclusions_stay_consistent(self):
        import example_audit_policy as policy
        import visible_screw_policy_v3 as visible
        prior = visible.BANK, visible.CONFIG, policy.BANK
        self.addCleanup(lambda: (setattr(visible, 'BANK', prior[0]), setattr(visible, 'CONFIG', prior[1]), setattr(policy, 'BANK', prior[2])))
        parts = np.ones((127,8,2,384), np.float32)
        review = np.ones((112,8,2,384), np.float32)
        policy.configure(parts, {'target_min': .05}, review)
        for name in ('reference','aligned','source'):
            Image.new('RGB', (30,30), 'white').save(self.root/(name+'.png'))
        c = dict(id=1, x=5, y=5, w=8, h=8, priority='high', wire_review=True,
                 source_polygon=[[5,5],[13,5],[13,13],[5,13]],
                 classification=dict(filter_recommendation='keep', action='manual_review'))
        excluded = dict(c, id=2, classification=dict(filter_recommendation='exclude', action='discard'))
        result = dict(candidates=[c], filtered_candidates=[excluded], pre_ai_count=2,
                      proposal_count=1, filtered_count=1, high_count=1, review_count=0,
                      wire_review_count=1, preview_scale=1)
        original = copy.deepcopy(result)
        def classify(snapshot, ref, target, baseline, *args, **kwargs):
            return baseline if baseline['filter_recommendation']=='exclude' else dict(
                filter_recommendation='exclude', action='discard', alarm_review5r={})
        with patch('live5r_review.review_alarm', side_effect=classify):
            after = ReviewBundle(self.root).apply(self.base, result, self.root, review, {})
        self.assertEqual(result, original)
        self.assertEqual(after['proposal_count'], 0)
        self.assertEqual(after['filtered_count'], 2)
        self.assertEqual(after['high_count']+after['review_count']+after['wire_review_count'], 0)
        self.assertEqual(next(c for c in after['filtered_candidates'] if c['id']==2), excluded)
        self.assertIs(visible.BANK, parts)
        self.assertIs(policy.BANK, review)
        self.assertTrue((self.root/after['local_review5r']['baseline_file']).is_file())
        for name in ('overlay','all_overlay'):
            self.assertTrue(np.array_equal(np.asarray(Image.open(self.root/(name+'.png'))), np.asarray(Image.open(self.root/'source.png'))))


if __name__ == '__main__':
    unittest.main()
