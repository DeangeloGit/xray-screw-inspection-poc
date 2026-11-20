from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
import numpy as np

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'experiments/dino'),str(Path(__file__).resolve().parents[1])]
from enclosure_rescue5r import geometry, review


def prediction(target=.1, reference=-.1):
    return dict(status='active',filter_recommendation='keep' if target>=0 and reference<0 else 'exclude',
                paired_evidence=dict(target=dict(label='screw' if target>=0 else 'non_screw',screw_margin=target),
                                     reference=dict(label='screw' if reference>=0 else 'non_screw',screw_margin=reference)))


class RescueTests(unittest.TestCase):
    def test_retained_and_non_enclosure_candidates_are_untouched(self):
        for recovery,decision in [('5r_enclosure','keep'),(None,'exclude')]:
            old=dict(filter_recommendation=decision)
            c=dict(recovery=recovery,classification=old,w=12,h=12)
            self.assertIs(review(None,None,None,c),old)

    def test_large_candidate_is_not_a_small_object_rescue(self):
        old=dict(filter_recommendation='exclude')
        self.assertIs(review(None,None,None,dict(recovery='5r_enclosure',classification=old,w=4,h=50)),old)

    def test_geometry_rejects_background_line_and_accepts_stable_object(self):
        a=np.ones((100,100),np.float32);a[43:57,44:56]=.1
        c=dict(x=44,y=43,w=12,h=14)
        found=geometry(a,c)
        self.assertEqual(found['extent'],[44,43,12,14])
        a[:,48:52]=.1
        self.assertIsNone(geometry(a,c))

    def test_both_crops_and_both_reference_decisions_are_required(self):
        old=dict(filter_recommendation='exclude');c=dict(x=20,y=20,w=12,h=12,recovery='5r_enclosure',classification=old)
        image=np.ones((60,60),np.float32);shape=dict(extent=[20,20,12,12],windows=[])
        for responses in [[prediction(),prediction(-.01)], [prediction(),prediction(.1,.01)]]:
            snapshot=Mock();snapshot.classify.side_effect=responses
            with patch('enclosure_rescue5r.geometry',return_value=shape):
                self.assertIs(review(snapshot,image,image,c),old)
            self.assertEqual(snapshot.classify.call_count,2)

    def test_success_preserves_old_evidence_and_uses_conservative_pair(self):
        old=dict(filter_recommendation='exclude');c=dict(x=20,y=20,w=12,h=12,recovery='5r_enclosure',classification=old)
        image=np.ones((60,60),np.float32);snapshot=Mock();snapshot.manifest={'model_id':'test'}
        snapshot.classify.side_effect=[prediction(.2,-.2),prediction(.1,-.1)]
        with patch('enclosure_rescue5r.geometry',return_value=dict(extent=[20,20,12,12],windows=[])):
            result=review(snapshot,image,image,c)
        self.assertEqual(result['filter_recommendation'],'keep')
        self.assertEqual(result['enclosure_rescue5r']['previous'],old)
        self.assertEqual(result['screw_margin'],.1)
        self.assertEqual(old['filter_recommendation'],'exclude')


if __name__=='__main__':unittest.main()
