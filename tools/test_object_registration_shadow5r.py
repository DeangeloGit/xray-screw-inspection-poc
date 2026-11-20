from pathlib import Path
import sys,unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
import object_registration_shadow5r as p
class ObjectTests(unittest.TestCase):
 def scene(self):
  a=np.full((300,300),.9,np.float32);rng=np.random.default_rng(71)
  a[120:145,110:140]=rng.uniform(.05,.15,(25,30));a[165:190,160:190]=rng.uniform(.05,.15,(25,30))
  return a,dict(id=1,x=180,y=180,w=5,h=5)
 def test_separate_stable_regions(self):
  a,c=self.scene();s=p.segment(a,c);self.assertEqual(len(s['objects']),2)
  self.assertFalse(np.any(s['objects'][0]['mask']&s['objects'][1]['mask']))
 def test_boundary_not_invented(self):
  a,c=self.scene();a[:,:]=.1;s=p.segment(a,c)
  self.assertEqual(s['objects'],[]);self.assertGreater(s['border_components_unresolved'],0)
 def test_registration_and_candidate_exclusion(self):
  a,c=self.scene();c.update(x=125,y=130);t=p.warp(a,[[1,0,2],[0,1,-1]],[0,0,300,300]);s=p.segment(t,c);r=p.segment(a,c)
  f=p.fit_object(a,t,c,s,s['objects'][0],r,r['objects'][0],8)
  self.assertTrue(f['accepted_geometry']);np.testing.assert_allclose(f['matrix'],[[1,0,2],[0,1,-1]],atol=.01)
  t[126:139,121:134]=0;self.assertEqual(f,p.fit_object(a,t,c,s,s['objects'][0],r,r['objects'][0],8))
 def test_unknown_never_becomes_normal(self):
  a,c=self.scene()
  with patch('enclosure_rescue5r.geometry',return_value=None):r=p.review(a,a,c,a,{'selected_reference_id':'synthetic'})
  self.assertFalse(r['normal_state_confirmed']);self.assertFalse(r['automatic_exclusion_allowed']);self.assertEqual(r['recommendation'],'retain')
 def test_unowned_query_cannot_borrow_neighbour(self):
  a,c=self.scene();c.update(x=150,y=150)
  with patch('enclosure_rescue5r.geometry',return_value=None):r=p.review(a,a,c,a,{'selected_reference_id':'synthetic'})
  self.assertEqual(r['query_owners'],[]);self.assertFalse(r['geometric_evidence_passed']);self.assertNotIn('evaluation',r)
if __name__=='__main__':unittest.main()
