from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
import split_registration_shadow5r as policy


class SplitTests(unittest.TestCase):
    def scene(self):
        a=cv2.GaussianBlur(np.random.default_rng(112).random((360,360)).astype('float32'),(0,0),1)
        a=(a-a.min())/(a.max()-a.min());c=dict(id=1,x=175,y=170,w=12,h=18);cut=170
        left=policy.warp(a,[[1,0,2],[0,1,-1]],[0,0,360,360]);right=policy.warp(a,[[1,0,-3],[0,1,2]],[0,0,360,360])
        target=left.copy();target[:,cut:]=right[:,cut:]
        return a,target,c,cut

    def test_two_parts_recover_different_motions_within_same_bound(self):
        a,t,c,cut=self.scene()
        for side,shift in [('left',(2,-1)),('right',(-3,2))]:
            fit=policy.fit_part(a,t,c,cut,64,side)
            self.assertTrue(fit['accepted_geometry'])
            self.assertLessEqual(fit['maximum_motion'],policy.RULES['search'])
            np.testing.assert_allclose(fit['matrix'],[[1,0,shift[0]],[0,1,shift[1]]],atol=.01)

    def test_query_pixels_cannot_steer_fit(self):
        a,t,c,cut=self.scene();before=policy.fit_part(a,t,c,cut,64,'right')
        t[166:192,171:191]=0
        self.assertEqual(before,policy.fit_part(a,t,c,cut,64,'right'))

    def test_rigid_rotation_is_recovered_without_scaling(self):
        a,t,c,cut=self.scene()
        matrix=cv2.getRotationMatrix2D((210.,179.),2.,1.)
        matrix[:,2]+=(-3,2)
        rotated=policy.warp(a,matrix,[0,0,360,360]);t[:,cut:]=rotated[:,cut:]
        fit=policy.fit_part(a,t,c,cut,64,'right')
        self.assertTrue(fit['accepted_geometry'])
        self.assertGreater(fit['heldout_correlation'],.98)
        points=np.array([[175,170],[186,187],[245,240]],np.float64)
        np.testing.assert_allclose(policy.transform_points(fit['matrix'],points),policy.transform_points(matrix,points),atol=1.)
        self.assertAlmostEqual(float(np.linalg.det(np.asarray(fit['matrix'])[:,:2])),1.,places=6)

    def test_successful_geometry_does_not_confirm_normality(self):
        a,t,c,cut=self.scene()
        with patch('enclosure_rescue5r.geometry',return_value=None),patch.object(policy,'separator',return_value={'x':cut}):
            result=policy.review(a,t,c,a,{'selected_reference_id':'synthetic-OK'})
        self.assertTrue(result['geometric_evidence_passed'])
        self.assertFalse(result['normal_state_confirmed'])
        self.assertFalse(result['automatic_exclusion_allowed'])
        self.assertEqual(result['recommendation'],'retain')

    def test_blank_and_boundary_abstain(self):
        a=np.zeros((360,360),np.float32)
        self.assertFalse(policy.fit_part(a,a,dict(x=175,y=170,w=12,h=18),170,64,'left')['valid'])
        self.assertFalse(policy.fit_part(a,a,dict(x=2,y=2,w=12,h=18),20,64,'right')['valid'])


if __name__=='__main__':unittest.main()
