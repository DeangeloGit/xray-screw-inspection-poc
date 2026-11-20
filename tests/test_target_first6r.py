import sys,unittest
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
from target_first6r import organize

def seed(i,x,y,w=3,h=3):return dict(id=i,seed=dict(x=x,y=y,w=w,h=h))
class TargetFirstTests(unittest.TestCase):
 def test_correspondence_not_required_and_sources_preserved(self):
  a=np.full((90,90),255,np.uint8);cv2.circle(a,(40,40),8,0,-1)
  s=[seed('a',37,38),seed('b',41,38)]
  d=organize(a,s)
  self.assertEqual(d['groups'][0]['members'],['a','b'])
  self.assertEqual([r['id'] for r in d['rows']],['a','b'])
  self.assertFalse(d['groups'][0]['official_alarm'])
 def test_open_structure_is_preserved_unknown(self):
  a=np.full((90,90),255,np.uint8);a[:,39:44]=0
  d=organize(a,[seed('a',40,40)])
  self.assertEqual(d['groups'],[])
  self.assertEqual(d['rows'][0]['unresolved_action'],'preserve_for_review')
 def test_nearby_objects_do_not_merge(self):
  a=np.full((90,90),255,np.uint8)
  for x in [35,46]:cv2.circle(a,(x,40),4,0,-1)
  self.assertEqual(len(organize(a,[seed('a',34,39,2,2),seed('b',45,39,2,2)])['groups']),2)
if __name__=='__main__':unittest.main()
