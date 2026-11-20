from pathlib import Path
import sys
import unittest
import copy
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
import structure_cause_shadow5r as policy


class CauseTests(unittest.TestCase):
    def scene(self):
        a=cv2.GaussianBlur(np.random.default_rng(73).random((300,300)).astype('float32'),(0,0),1)
        a=(a-a.min())/(a.max()-a.min())
        return a,.8*np.roll(a,3,axis=1)+.05,dict(id=1,x=140,y=140,w=12,h=18)

    def test_separate_translation_and_exposure(self):
        a,b,c=self.scene();rows=policy.ablation(a,a,b,c,16,-3,0)['stages']
        self.assertLess(rows[-1]['outside_MAE'],1e-6)
        self.assertAlmostEqual(rows[-1]['gain'],.8,places=5)
        self.assertGreater(rows[1]['outside_MAE'],rows[-1]['outside_MAE'])
        self.assertGreater(rows[2]['outside_MAE'],rows[-1]['outside_MAE'])

    def test_grid_excludes_candidate_content(self):
        a,b,c=self.scene();box=[120,120,180,190];old=policy.grid_match(a,b,c,box)
        b[136:162,136:156]=0
        self.assertEqual(old,policy.grid_match(a,b,c,box))

    def test_diagnosis_never_removes_alarm_or_changes_input(self):
        a,b,c=self.scene();old=copy.deepcopy(c)
        result=policy.diagnose(a,b,c,None,{})
        self.assertEqual(result['recommendation'],'retain')
        self.assertFalse(result['automatic_exclusion_allowed'])
        self.assertEqual(c,old)


if __name__=='__main__':unittest.main()
