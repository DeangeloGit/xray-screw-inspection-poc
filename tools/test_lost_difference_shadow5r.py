"""Safety/causal controls for an offline observation channel."""
import sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'experiments/dino')]
import numpy as np,cv2
from lost_difference_shadow5r import analyze
class Controls(unittest.TestCase):
 def fixture(self):
  rng=np.random.default_rng(7);r=cv2.GaussianBlur(rng.uniform(.25,.85,(160,160)).astype('float32'),(0,0),2)
  cv2.circle(r,(80,85),10,.12,-1);cv2.rectangle(r,(35,30),(44,120),.18,-1)
  return r
 def test_identity_has_no_observations(self):
  r=self.fixture();self.assertEqual(analyze(r,r.copy(),np.ones(r.shape,bool))['rows'],[])
 def test_context_recovers_known_translation(self):
  from ok_reference_shadow5r import context_match
  r=self.fixture();t=cv2.warpAffine(r,np.float32([[1,0,2],[0,1,1]]),(160,160),borderValue=1)
  for pad in (16,32):
   v=context_match(r,t,dict(x=77,y=74,w=12,h=18),pad)
   self.assertTrue(v['valid']);self.assertEqual((v['dx'],v['dy']),(-2,-1));self.assertGreater(v['score'],.99)
 def test_no_coverage_has_no_observations(self):
  r=self.fixture();t=r.copy();cv2.circle(t,(80,70),8,.1,-1)
  self.assertEqual(analyze(r,t,np.zeros(r.shape,bool))['rows'],[])
 def test_inputs_unchanged_and_never_an_alarm(self):
  r=self.fixture();t=r.copy();cv2.circle(t,(80,70),8,.1,-1);a=r.copy();b=t.copy();out=analyze(r,t,np.ones(r.shape,bool))
  np.testing.assert_array_equal(r,a);np.testing.assert_array_equal(t,b);self.assertFalse(out['official_decisions_changed']);self.assertTrue(all(not c['official_alarm'] and not c['dino_evaluated'] for c in out['rows']))
if __name__=='__main__':unittest.main()
