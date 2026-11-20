import sys,unittest
from pathlib import Path
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
from joint_boundary6r import region,analyze_seed,mask_iou

class JointTests(unittest.TestCase):
 def setUp(self):
  self.ref=np.full((100,100),180,np.uint8)
  cv2.circle(self.ref,(50,63),7,20,-1)
  self.target=self.ref.copy();cv2.circle(self.target,(50,48),7,20,-1)
  self.seed=dict(x=47,y=45,w=6,h=6)
  self.context=dict(dx=0,dy=0,gain=1,offset=0,pad=16)
 def test_shared_structure_does_not_become_foreground(self):
  for method in ['watershed','graphcut']:
   result,(mask,(x,y))=region(self.ref,self.target,self.seed,self.context,20,.13,method)
   self.assertTrue(result['core_preserved']); self.assertFalse(mask[63-y,50-x])
 def test_unchanged_image_has_no_positive_seed(self):
  result,_=region(self.ref,self.ref,self.seed,self.context,20,.13)
  self.assertEqual(result['reason'],'no_corrected_seed')
 def test_image_boundary_is_unknown(self):
  result,_=region(self.ref,self.target,dict(x=2,y=2,w=3,h=3),self.context,20,.13)
  self.assertFalse(result['valid'])
 def test_weak_context_never_promotes(self):
  result,_=analyze_seed(self.ref,self.target,self.seed,contexts=[dict(valid=False),dict(valid=False)])
  self.assertEqual(result['status'],'uncertain_correspondence')
 def test_graphcut_is_deterministic_and_read_only(self):
  old=self.target.copy()
  a,am=region(self.ref,self.target,self.seed,self.context,20,.13,'graphcut')
  b,bm=region(self.ref,self.target,self.seed,self.context,20,.13,'graphcut')
  self.assertEqual(a,b);self.assertEqual(mask_iou(am,bm),1)
  np.testing.assert_array_equal(old,self.target)
 def test_disjoint_masks_never_overlap(self):
  m=np.ones((5,5),bool)
  self.assertEqual(mask_iou((m,(0,0)),(m,(7,0))),0)

if __name__=='__main__':unittest.main()
