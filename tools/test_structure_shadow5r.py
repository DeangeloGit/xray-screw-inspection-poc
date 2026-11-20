import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
import structure_shadow5r as policy


class ShadowTests(unittest.TestCase):
    def scene(self):
        rng=np.random.default_rng(11)
        ref=cv2.GaussianBlur(rng.random((160,160)).astype('float32'),(0,0),1)
        ref=(ref-ref.min())/(ref.max()-ref.min())
        target=np.roll(ref,3,axis=1)
        return ref,target,dict(id=7,x=65,y=65,w=12,h=18)

    def test_surrounding_registration_and_added_object(self):
        ref,target,c=self.scene()
        clean=policy.match(ref,target,c,16)
        self.assertEqual((clean['dx'],clean['dy']),(-3,0))
        self.assertLess(clean['remaining_fraction'],.01)
        self.assertEqual(policy.review(ref,target,c)['recommendation'],'exclude_suggestion')
        target[65:83,65:77]=0
        changed=policy.match(ref,target,c,16)
        self.assertEqual((changed['dx'],changed['dy']),(-3,0))
        self.assertGreaterEqual(changed['largest_residual_component'],20)
        self.assertEqual(policy.review(ref,target,c)['recommendation'],'retain')

    def test_shadow_cannot_change_candidates_or_counts(self):
        ref,target,c=self.scene();result=dict(candidates=[c],filtered_candidates=[dict(id=9)],proposal_count=1)
        previous=copy.deepcopy(result)
        with tempfile.TemporaryDirectory() as d:
            for name,a in [('reference',ref),('aligned',target)]:Image.fromarray(np.rint(a*255).astype('uint8')).save(Path(d)/(name+'.png'))
            with patch.object(policy,'review',return_value=dict(candidate_id=7,recommendation='exclude_suggestion')):
                out=policy.apply(result,d)
            self.assertEqual(result,previous)
            self.assertEqual({k:out[k] for k in result},previous)
            self.assertEqual(out['structure_shadow5r']['suggested_exclusions'],[7])
            self.assertFalse(json.loads((Path(d)/'structure-shadow.json').read_text())['official_decisions_changed'])

    def test_low_texture_and_boundary_abstain(self):
        a=np.ones((160,160),np.float32)
        self.assertFalse(policy.match(a,a,dict(x=65,y=65,w=12,h=18),16)['valid'])
        self.assertFalse(policy.match(a,a,dict(x=2,y=2,w=12,h=18),16)['valid'])


if __name__=='__main__':unittest.main()
