import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('boundary6r', Path(__file__).resolve().parents[1]/'experiments/dino/boundary_shadow6r.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BoundaryAuditTests(unittest.TestCase):
    def seeds(self):
        return [dict(id=i, seed=dict(x=x,y=25,w=3,h=3)) for i,x in enumerate((25,32),1)]

    def test_same_closed_component_has_shared_evidence(self):
        image=np.full((70,70),255,np.uint8); image[23:31,23:38]=0
        old=image.copy(); result=module.analyze(image,self.seeds())
        self.assertTrue(result['merge_hypotheses'])
        self.assertTrue(all(g['seed_ids']==[1,2] for g in result['merge_hypotheses']))
        np.testing.assert_array_equal(old,image)

    def test_nearby_separate_shapes_are_not_merged(self):
        image=np.full((70,70),255,np.uint8)
        image[23:31,23:29]=0; image[23:31,31:38]=0
        self.assertEqual(module.analyze(image,self.seeds())['merge_hypotheses'],[])

    def test_board_connection_stays_unknown(self):
        image=np.full((70,70),255,np.uint8); image[23:31,:]=0
        result=module.analyze(image,self.seeds())
        self.assertTrue(all(r['boundary_status']=='unknown' and r['object_box'] is None for r in result['rows']))
        self.assertEqual(result['merge_hypotheses'],[])

    def test_one_intensity_level_is_not_stability(self):
        image=np.full((70,70),40,np.uint8); image[23:31,23:38]=0
        self.assertFalse(module.analyze(image,self.seeds())['merge_hypotheses'])


if __name__=='__main__': unittest.main()
