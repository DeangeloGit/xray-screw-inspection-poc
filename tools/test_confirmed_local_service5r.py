"""Integration safeguards with synthetic data, separate from real-image runs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'experiments/dino'),str(ROOT)]
import confirmed_local_service5r as service
from folder_batch5r import report, verify_report


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.pkg=self.root/'pkg';self.pkg.mkdir()
        self.run=self.root/'runs'/'000000';self.run.mkdir(parents=True)
        a=np.random.default_rng(19).integers(40,150,(180,180),dtype=np.uint8)
        original=a.copy();original[85:93,85:91]+=70
        for name,data in [('aligned.png',a),('reference.png',original)]:Image.fromarray(data).save(self.run/name)
        self.golden=self.run/'reference.png';self.target=self.run/'aligned.png'
        refs=[]
        for i in (1,2):
            source=self.pkg/f'source{i}.png';b=a.copy();b[0,0]=i;Image.fromarray(b).save(source)
            aligned=self.pkg/f'aligned{i}.png';Image.fromarray(a).save(aligned)
            refs.append(dict(id=str(i),machine='MPT10',reference_sha256=service.sha(self.golden),source_file=source.name,source_sha256=service.sha(source),aligned_file=aligned.name,aligned_sha256=service.sha(aligned),local_normal_confirmed=True,whole_image_normal_confirmed=False,confirmed_normal_bbox=[82,82,96,98]))
        self.meta=dict(schema_version=1,mode='suggestion_only',machine='MPT10',automatic_exclusion=False,scope='confirmed_U1_only',reference_sha256=service.sha(self.golden),references=refs,policies={'confirmed_local_reference_shadow5r.py':service.sha(ROOT/'experiments/dino/confirmed_local_reference_shadow5r.py')})
        self.write_meta()
        self.result=dict(candidates=[dict(id=1,x=85,y=85,w=6,h=8,classification={'filter_recommendation':'keep'})],filtered_candidates=[],pre_ai_count=1,proposal_count=1,high_count=1,matrix=[[1,0,0],[0,1,0]],alignment_warning=False)

    def write_meta(self):
        p=self.pkg/'manifest.json';p.write_text(json.dumps(self.meta),encoding='utf8');self.review=service.LocalReferenceReview(self.pkg,service.sha(p))

    def apply(self):
        before=copy.deepcopy(self.result)
        with patch('enclosure_rescue5r.geometry',return_value=None):r=self.review.apply(self.result,self.run,self.golden,self.target)
        self.assertEqual(self.result,before)
        for k in self.result:self.assertEqual(r[k],self.result[k])
        self.assertFalse(r['confirmed_local_review5r']['automatic_exclusion'])
        return r

    def test_suggestion_preserves_every_original_field_and_report_alarm(self):
        r=self.apply();self.assertEqual(r['confirmed_local_review5r']['suggested_exclusions'],[1])
        (self.run/'result.json').write_text(json.dumps(r),encoding='utf8')
        job=dict(machine={'name':'MPT10'},folder='synthetic',label='NG',rows=[dict(id='000000',file='test.png',status='done',is_reference=False,label='NG',kept=1,removed=0,alignment_warning=False)])
        (self.root/'job.json').write_text(json.dumps(job),encoding='utf8')
        expected=report(self.root,job);verify_report(self.root,expected)
        page=(self.root/'photo-000000.html').read_text('utf8')
        self.assertIn('建議排除，但正式警報仍保留',page);self.assertIn('保留警報',page)
        self.assertEqual(expected['summary']['ng_missed'],0)

    def test_missing_reference_keeps_original(self):
        (self.pkg/'aligned1.png').unlink();r=self.apply()
        self.assertEqual(r['confirmed_local_review5r']['status'],'unavailable')
        self.assertEqual(r['confirmed_local_review5r']['suggested_exclusions'],[])

    def test_file_tampering_is_rechecked_not_cached(self):
        self.assertTrue(self.review.status()['ready']);(self.pkg/'aligned1.png').write_bytes(b'changed')
        self.assertFalse(self.review.status()['ready']);self.assertEqual(self.apply()['confirmed_local_review5r']['suggested_exclusions'],[])

    def test_manifest_auto_mode_cannot_enable_removal(self):
        self.meta['automatic_exclusion']=True;self.write_meta()
        self.assertEqual(self.apply()['confirmed_local_review5r']['status'],'unavailable')

    def test_alignment_failure_and_exception_keep_alarm(self):
        with patch.object(service.policy,'context_match',return_value={'valid':False,'reason':'failed'}):
            self.assertEqual(self.apply()['confirmed_local_review5r']['suggested_exclusions'],[])
        self.result['matrix']=[[float('nan'),0,0],[0,1,0]]
        self.assertEqual(self.apply()['confirmed_local_review5r']['status'],'unavailable')

    def test_other_golden_not_applicable_and_no_fallback_reference(self):
        self.meta['reference_sha256']='other'
        for ref in self.meta['references']:ref['reference_sha256']='other'
        self.write_meta();self.assertEqual(self.apply()['confirmed_local_review5r']['status'],'not_applicable')

    def test_manifest_digest_mismatch_keeps_original(self):
        (self.pkg/'manifest.json').write_text('{}',encoding='utf8')
        self.assertEqual(self.apply()['confirmed_local_review5r']['status'],'unavailable')

if __name__=='__main__':unittest.main()
