"""Known local movement is explainable; extra objects cannot fit themselves away."""
import cv2
import numpy as np
import json
from pathlib import Path
from single_reference_evidence import explain

def run():
    rng=np.random.default_rng(72)
    ref=cv2.GaussianBlur(rng.uniform(.2,.95,(180,180)).astype('float32'),(0,0),1)
    cv2.rectangle(ref,(75,75),(86,88),.15,-1)
    target=cv2.warpAffine(ref,np.float32([[1,0,8],[0,1,-5]]),(180,180),borderValue=.8)
    c=dict(x=83,y=70,w=12,h=14)
    evidence=explain(ref,target,c,.13)
    assert evidence and evidence['dx']==-8 and evidence['dy']==5,evidence
    added=target.copy();cv2.rectangle(added,(83,70),(94,83),.01,-1)
    assert explain(ref,added,c,.13) is None,'extra attenuation explained away'
    c2=dict(x=115,y=95,w=12,h=14)
    cv2.rectangle(added,(115,95),(126,108),.02,-1)
    assert explain(ref,added,c2,.13) is None,'new object explained away'
    assert explain(ref,target,dict(x=0,y=0,w=12,h=14),.13) is None
    flat=np.ones_like(ref)*.7
    assert explain(flat,flat,c,.13) is None,'untextured context accepted'
    corpus=Path('workspace/windows-check/diagnostics/collected-data/single-reference-experiment.json')
    if corpus.exists():
        cases=json.loads(corpus.read_text(encoding='utf-8'))
        assert all(not r['removed'] for r in cases if '/NG/' in r['relative']), 'NG candidate removed; inspect before release'
        for row in cases:
            if not row['removed']:continue
            arrays=np.load(row['alignment'])
            for candidate in row['removed']:
                target=arrays['target'].copy()
                x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
                target[y:y+h,x:x+w]=np.clip(target[y:y+h,x:x+w]-.3,0,1)
                assert explain(arrays['ref'],target,candidate,.13) is None, row['relative']
    print('PASS: shifted structure, extra attenuation, new object, boundary and untextured context')

if __name__=='__main__':run()
