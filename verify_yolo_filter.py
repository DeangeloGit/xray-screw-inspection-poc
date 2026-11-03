"""Run the real difference pipeline with an isolated synthetic YOLO, never activate it."""
import json,tempfile
from pathlib import Path
import numpy as np
import onnxruntime as ort
from verify_model_adapters import fixture
from model_manager import Snapshot
from detector import detect
root=Path(__file__).resolve().parent
rows=json.loads((root/'workspace/windows-check/diagnostics/v11-examples-full-evaluation-20261103/results.json').read_text(encoding='utf-8'))
r=next(x for x in rows if '15_53_47_24' in x['path'])
m=dict(model_id='isolated-yolo-test',backend='yolo_onnx',preprocessing='aligned-gray-tight12-v1',classes=['screw'],screw_class_id=0,input_size=[640,640],confidence=.25)
options=ort.SessionOptions();options.intra_op_num_threads=2
s=ort.InferenceSession(fixture([1,5,1],[320,320,200,200,.05]),sess_options=options,providers=['CPUExecutionProvider'])
snapshot=Snapshot(m,'synthetic-test',s)
with tempfile.TemporaryDirectory(prefix='xray-yolo-filter-') as tmp:
 result=detect(Path(r['reference']),Path(r['path']),'yolo-filter-integration',model_snapshot=snapshot,output_directory=Path(tmp))
 assert result['pre_ai_count']==5 and result['filtered_count']==5 and result['proposal_count']==0
 assert result['model']['mode']=='auto_filter'
 assert all(c['classification']['label']=='non_screw' and c['classification']['action']=='discard' for c in result['filtered_candidates'])
 assert (Path(tmp)/'all_overlay.png').read_bytes()==(Path(tmp)/'source.png').read_bytes()
 assert (Path(tmp)/'crop_1.png').exists()
failed=Snapshot(m,'broken',object()).classify(np.ones((80,80),np.float32),candidate_box=[30,30,40,40])
assert failed['status']=='error' and failed['action']=='manual_review'
print('PASS: actual difference pipeline -> YOLO -> removal of 5 candidates, overlays cleared, audit crops retained, inference errors retained')
