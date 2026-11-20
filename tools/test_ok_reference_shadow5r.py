from pathlib import Path
import sys
import unittest
import cv2
import numpy as np

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'experiments/dino')]
import structure_shadow5r as previous
import ok_reference_shadow5r as policy


class ReferenceTests(unittest.TestCase):
    def scene(self):
        rng=np.random.default_rng(35)
        a=cv2.GaussianBlur(rng.random((160,160)).astype('float32'),(0,0),1)
        a=(a-a.min())/(a.max()-a.min())
        return a,np.roll(a,3,axis=1),dict(id=1,x=65,y=65,w=12,h=18)

    def test_fast_search_agrees_with_frozen_search(self):
        a,b,c=self.scene()
        for pad in previous.RULES['pads']:
            old=previous.match(a,b,c,pad);new=policy.context_match(a,b,c,pad)
            for k in ('dx','dy'):self.assertEqual(old[k],new[k])
            for k in ('score','gain','offset'):self.assertAlmostEqual(old[k],new[k],places=5)

    def test_target_candidate_cannot_influence_selection(self):
        a,b,c=self.scene();before=[policy.context_match(a,b,c,p) for p in previous.RULES['pads']]
        b[61:87,61:81]=0
        self.assertEqual(before,[policy.context_match(a,b,c,p) for p in previous.RULES['pads']])

    def test_non_OK_other_machine_self_and_duplicates_excluded(self):
        base=dict(id='a',label='OK',machine='M',reference_sha256='ref',source_sha256='a')
        pool=[base,dict(base,id='dup'),dict(base,id='ng',label='NG',source_sha256='ng'),
              dict(base,id='self',source_sha256='self'),dict(base,id='other',machine='X',source_sha256='other'),
              dict(base,id='reference',is_reference=True,source_sha256='golden')]
        q=dict(machine='M',reference_sha256='ref',source_sha256='self')
        self.assertEqual([v['id'] for v in policy.eligible_references(pool,q)],['a'])

    def test_boundary_and_blank_abstain(self):
        a=np.zeros((100,100),np.float32)
        for c in [dict(x=1,y=1,w=10,h=10),dict(x=40,y=40,w=10,h=10)]:
            self.assertFalse(policy.context_match(a,a,c,16)['valid'])


if __name__=='__main__':unittest.main()
