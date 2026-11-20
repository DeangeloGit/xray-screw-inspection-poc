from pathlib import Path
import sys, unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/dino'))
import confirmed_local_reference_shadow5r as p

class LocalReferenceTests(unittest.TestCase):
    def scene(self):
        t=np.random.default_rng(19).uniform(.1,.6,(180,180)).astype('float32')
        c=dict(id=1,x=85,y=85,w=6,h=8)
        original=t.copy();original[85:93,85:91]+=.3
        refs=[dict(id=str(i),machine='M',reference_sha256='golden',source_sha256=str(i),
                   local_normal_confirmed=True,confirmed_normal_bbox=[82,82,96,98]) for i in [1,2]]
        query=dict(machine='M',reference_sha256='golden',source_sha256='target')
        return original,t,c,refs,query

    def run_review(self,o,t,c,refs,q,images=None):
        with patch('enclosure_rescue5r.geometry',return_value=None):
            return p.review(o,t,c,refs,q,lambda r:images[r['id']] if images else t)

    def test_existing_gates_pass_without_changing_decision(self):
        o,t,c,refs,q=self.scene();r=self.run_review(o,t,c,refs,q)
        self.assertTrue(r['both_references_passed']);self.assertEqual(r['recommendation'],'exclude_suggestion')
        self.assertFalse(r['automatic_exclusion_allowed']);self.assertFalse(r['target_human_normal_confirmed'])

    def test_self_reference_cannot_supply_confirmation(self):
        o,t,c,refs,q=self.scene();q['source_sha256']='1'
        self.assertEqual(self.run_review(o,t,c,refs,q)['recommendation'],'retain')

    def test_local_confirmation_cannot_label_other_region(self):
        o,t,c,refs,q=self.scene();c['x']=100
        self.assertEqual(self.run_review(o,t,c,refs,q)['recommendation'],'retain')
        self.assertFalse(p.covered(dict(x=90,y=85,w=6,h=8),refs[0]['confirmed_normal_bbox'],1,0))
        c['x']=90
        fit=dict(valid=True,pad=16,score=1.,dx=5,dy=0,gain=1.,offset=0.)
        with patch.object(p,'context_match',return_value=fit),patch.object(p,'ablation',side_effect=AssertionError('must not sample outside annotation')):
            measured=p.compare(o,t,c,t,refs[0])
        self.assertFalse(measured['local_label_covered']);self.assertFalse(measured['passed'])

    def test_both_references_must_explain_candidate(self):
        o,t,c,refs,q=self.scene();bad=t.copy();bad[85:93,85:91]+=.3
        r=self.run_review(o,t,c,refs,q,{'1':t,'2':bad})
        self.assertTrue(r['comparisons'][0]['passed']);self.assertFalse(r['comparisons'][1]['passed'])
        self.assertEqual(r['recommendation'],'retain')

    def test_machine_and_unconfirmed_reference_fail_closed(self):
        o,t,c,refs,q=self.scene();refs[0]['local_normal_confirmed']=False
        self.assertEqual(self.run_review(o,t,c,refs,q)['recommendation'],'retain')
        refs[0]['local_normal_confirmed']=True;q['machine']='other'
        self.assertEqual(self.run_review(o,t,c,refs,q)['recommendation'],'retain')

    def test_stable_object_protected_before_background_match(self):
        o,t,c,refs,q=self.scene()
        with patch('enclosure_rescue5r.geometry',return_value={'extent':[85,85,6,8]}):
            r=p.review(o,t,c,refs,q,lambda r:self.fail('protected object must not load normal reference'))
        self.assertEqual(r['reason'],'independent_object_protected')

if __name__=='__main__':unittest.main()
