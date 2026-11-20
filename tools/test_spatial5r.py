"""Geometry and safety-contract tests; actual accuracy is separately regressed."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'experiments/dino'),
               str(Path(__file__).resolve().parents[1])]
from spatial5r import enclosure_mask, review_fragment, stable_core
from enclosure_guard5r import review as review_enclosure
from fragment_core_guard5r import review as protect_core


class SpatialTests(unittest.TestCase):
    def test_uncertain_compact_object_preserves_original_paired_alarm(self):
        original={'filter_recommendation':'keep','paired_evidence':{'verified':'original'}}
        veto={'filter_recommendation':'exclude','spatial_review5r':{'accepted':True,'previous':original}}
        c=dict(x=10,y=10,w=15,h=15,classification=veto)
        with patch('correspondence_geometry.contours',return_value=[dict(box=[10,10,13,14],coverage=.64)]), patch('dino_paired_optimized.classify_candidate',return_value={'filter_recommendation':'exclude'}):
            result=protect_core(None,None,None,c)
        self.assertEqual(result['filter_recommendation'],'keep')
        self.assertEqual(result['paired_evidence'],original['paired_evidence'])
        self.assertEqual(veto['filter_recommendation'],'exclude')

    def test_core_guard_does_not_change_old_exclusion_or_unsupported_fragment(self):
        original={'filter_recommendation':'exclude'}
        self.assertIs(protect_core(None,None,None,{'classification':original}),original)
        veto={'filter_recommendation':'exclude','spatial_review5r':{'accepted':True,'previous':{'filter_recommendation':'keep'}}}
        with patch('correspondence_geometry.contours',return_value=[]):
            self.assertEqual(protect_core(None,None,None,{'classification':veto})['filter_recommendation'],'exclude')

    def test_faint_enclosure_is_included_without_external_object(self):
        reference=np.ones((160,160),np.float32)
        original=np.zeros((160,160),bool)
        original[35:125,45:115]=True
        reference[original]=.5
        cv2.rectangle(reference,(39,29),(121,131),.90,2)
        cv2.rectangle(reference,(140,35),(154,125),.05,3)
        before=original.copy()
        result=enclosure_mask(reference,original)
        self.assertTrue(np.all(result[original]))
        self.assertTrue(result[80,120])
        self.assertFalse(result[80,145])
        np.testing.assert_array_equal(original,before)

    def test_empty_reference_scope_is_an_error(self):
        with self.assertRaises(ValueError):
            enclosure_mask(np.ones((50,50),np.float32),np.zeros((50,50),bool))

    def test_core_requires_two_distinct_levels_on_the_same_object(self):
        a=dict(box=[10,10,10,10],coverage=.9,cutoff=.2)
        self.assertFalse(stable_core([a,dict(a)]))
        self.assertFalse(stable_core([a,dict(a,box=[30,30,10,10],cutoff=.3)]))
        self.assertTrue(stable_core([a,dict(a,box=[10,10,11,10],cutoff=.3)]))

    def test_prior_exclusion_never_changes(self):
        old=dict(filter_recommendation='exclude',reason='unchanged')
        candidate=dict(classification=old)
        self.assertIs(review_fragment(None,None,None,candidate),old)

    def test_edge_candidate_and_long_wire_core_are_not_fragment_vetoed(self):
        old=dict(filter_recommendation='keep')
        for box,recovery in [([10,10,15,89],None),([10,10,10,12],'5r_enclosure')]:
            c=dict(zip(('x','y','w','h'),box),classification=old,recovery=recovery)
            self.assertIs(review_fragment(None,None,None,c),old)

    def test_stable_screw_core_bypasses_parent_background_classification(self):
        old=dict(filter_recommendation='keep')
        c=dict(x=10,y=10,w=10,h=10,classification=old)
        shapes=[dict(box=[10,10,10,10],coverage=1,cutoff=v) for v in [.2,.3]]
        with patch('correspondence_geometry.contours',return_value=shapes), patch('dino_paired_optimized.classify_candidate') as classifier:
            result=review_fragment(None,None,None,c)
            self.assertEqual(result['filter_recommendation'],'keep')
            classifier.assert_not_called()

    def test_enclosure_guard_never_relabels_an_original_alarm(self):
        old=dict(filter_recommendation='keep')
        candidate=dict(x=10,y=10,w=4,h=30,classification=old)
        self.assertIs(review_enclosure(None,None,None,candidate),old)

    def test_enclosure_sliver_without_object_support_is_excluded_with_evidence(self):
        old=dict(filter_recommendation='keep',paired_evidence={'target':{'label':'screw'}})
        candidate=dict(x=10,y=10,w=4,h=30,recovery='5r_enclosure',classification=old)
        with patch('local_object5r.compact_cores',return_value=[]):
            result=review_enclosure(None,None,None,candidate)
        self.assertEqual(result['filter_recommendation'],'exclude')
        self.assertEqual(old['filter_recommendation'],'keep')
        self.assertEqual(result['enclosure_guard5r']['previous'],old)

    def test_real_core_inside_long_enclosure_candidate_is_preserved(self):
        old=dict(filter_recommendation='keep')
        candidate=dict(x=10,y=10,w=15,h=89,recovery='5r_enclosure',classification=old)
        with patch('local_object5r.compact_cores',return_value=[{'box':[10,40,15,15]}]), patch('dino_paired_optimized.classify_candidate',return_value={'filter_recommendation':'keep'}):
            result=review_enclosure(None,None,None,candidate)
        self.assertEqual(result['filter_recommendation'],'keep')
        self.assertTrue(result['enclosure_guard5r']['supported'])


if __name__=='__main__':unittest.main()
