import unittest,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
from candidate_organizer6r import organize

def joint(boxes,shared=False):
 return dict(rows=[dict(id=str(i),graphcut=dict(shared_dark_boundary=shared)) for i in range(len(boxes))],
             groups=dict(graphcut=[dict(id=i,members=[str(i)],box=b) for i,b in enumerate(boxes)]))

class OrganizerTests(unittest.TestCase):
 def test_outer_contour_expands_core(self):
  image=np.full((90,90),255,np.uint8);cv2.circle(image,(40,40),8,0,-1)
  d=organize(image,joint([[38,38,4,4]]))
  self.assertEqual(len(d['groups']),1);self.assertGreater(d['groups'][0]['box'][2],4)
 def test_same_outer_contour_merges_fragments(self):
  image=np.full((90,90),255,np.uint8);cv2.circle(image,(40,40),8,0,-1)
  d=organize(image,joint([[37,38,3,4],[41,38,3,4]]))
  self.assertEqual(len(d['groups']),1);self.assertEqual(d['groups'][0]['members'],['0','1'])
 def test_nearby_separate_objects_remain_separate(self):
  image=np.full((90,90),255,np.uint8);cv2.circle(image,(35,40),4,0,-1);cv2.circle(image,(46,40),4,0,-1)
  self.assertEqual(len(organize(image,joint([[34,39,2,2],[45,39,2,2]]))['groups']),2)
 def test_shared_contact_is_evidence_not_a_veto(self):
  image=np.full((90,90),255,np.uint8);cv2.circle(image,(40,40),8,0,-1)
  d=organize(image,joint([[38,38,4,4]],True))
  self.assertEqual(len(d['groups']),1);self.assertTrue(d['groups'][0]['shared_dark_boundary'])
  self.assertFalse(d['rows'][0]['complete_object_verified'])

if __name__=='__main__':unittest.main()
