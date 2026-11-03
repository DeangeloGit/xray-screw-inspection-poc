"""Verify CLIP routing and actual production filtering on the reported OK sample."""
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from model_manager import Snapshot
from model_adapters import clip_decision
from detector import detect

snapshot=Snapshot({'model_id':'test','backend':'clip_onnx'}, 'test', object())
for scores,action in [([.3,.32],'discard'),([.3,.309],'manual_review'),([.32,.3],'manual_review')]:
    with patch('model_adapters.classify',return_value=clip_decision(['screw','cable'],scores)):
        assert snapshot.classify(np.zeros((32,32)))['action']==action
with patch('model_adapters.classify',side_effect=ValueError('test failure')):
    assert snapshot.classify(np.zeros((32,32)))['action']=='manual_review'

root=Path(__file__).resolve().parent
batch=root/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103'
rows=json.loads((batch/'results.json').read_text(encoding='utf-8'))
sample=next(r for r in rows if '15_53_47_24' in r['path'])
out=root/'workspace/windows-check/diagnostics/v11-clip-filter-check'
result=detect(Path(sample['reference']),Path(sample['path']),'clip-filter-check',threshold=.13,output_directory=out)
assert result['model']['mode']=='auto_filter' and not result['model']['error']
assert result['pre_ai_count']==5
assert result['proposal_count']+result['filtered_count']==5
assert all(c['classification']['action']=='discard' for c in result['filtered_candidates'])
assert all(c['classification']['action']!='discard' for c in result['candidates'])
assert {c['id'] for c in result['candidates']}.isdisjoint(c['id'] for c in result['filtered_candidates'])
all_candidates=result['candidates']+result['filtered_candidates']
wire=next(c for c in all_candidates if c['id']==1)['classification']
if wire.get('shape_evidence'):
    assert wire['label']=='cable' and wire['action']=='discard'
else:
    assert wire['label']=='uncertain'
print(json.dumps({k:result[k] for k in ('version','pre_ai_count','proposal_count','filtered_count')}))
print('PASS: clear non-screw discarded, screw/tie/error retained, production sample evaluated')
sample=next(r for r in rows if r['label']=='OK' and not r['is_reference'] and r['ai_non_screw']>0)
result=detect(Path(sample['reference']),Path(sample['path']),'clip-discard-check',threshold=.13,output_directory=out/'discard-case')
assert result['filtered_count']>0
assert result['proposal_count']+result['filtered_count']==result['pre_ai_count']
assert result['high_count']+result['review_count']==result['proposal_count']
assert all(c['classification']['action']=='discard' for c in result['filtered_candidates'])
print('PASS: actual CLIP discarded',result['filtered_count'],'of',result['pre_ai_count'],sample['relative'])
