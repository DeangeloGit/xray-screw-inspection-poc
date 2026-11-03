"""Visual exemplars only protect positive evidence; never add an automatic deletion."""
import numpy as np
from model_adapters import clip_decision,refine_screw_examples
from model_manager import Snapshot
from unittest.mock import patch

u=np.zeros(512,np.float32);u[0]=1
v=np.zeros(512,np.float32);v[1]=1
bank=dict(method='clip-visual-screw-bank-v1',neighbors=3,margin=.01,minimum_similarity=.85,
          screw=dict(ids=['a','b','c'],embeddings=[u.tolist()]*3),
          normal=dict(ids=['d','e','f'],embeddings=[v.tolist()]*3))
m={'model_id':'test','backend':'clip_onnx','screw_examples':bank}
for scores in ([.3,.4],[.3,.305],[.4,.3]):
    decision=clip_decision(['screw','cable'],scores)
    supported=refine_screw_examples(m,u,decision)
    assert supported['label']=='screw' and supported['filter_recommendation']=='keep'
    unsupported=refine_screw_examples(m,v,decision)
    assert unsupported['label']==decision['label']
    assert unsupported['filter_recommendation']==decision['filter_recommendation']
    assert refine_screw_examples({},u,decision)==decision
    with patch('model_adapters.classify',return_value=supported):
        assert Snapshot(m,'test',object()).classify(np.zeros((32,32)))['action']=='manual_review'
print('PASS: positive examples protect screws; unsupported appearance cannot introduce deletion; legacy models unchanged')
