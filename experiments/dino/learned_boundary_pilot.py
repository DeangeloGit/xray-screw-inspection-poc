"""Offline DINO linear classifier experiment; exact same 17 fixed pairs.

Select regularization by example-bank leave-one-out, never by the 17 test labels.
No example additions, no reference/target test crop is added to the bank.
"""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.local_added_object_pilot import read,save,OUT as PRIOR
from dino_adapter import embedding
OUT=ROOT/'workspace/dino-learned-boundary-20261103'
FOCUS=ROOT/'workspace/focused-object-pilot-20261103'

def fit(x,y,penalty):
    # Balanced classes and an unpenalized intercept.
    weights=np.where(y>0,.5/(y>0).sum(),.5/(y<0).sum())*len(y)
    mx=np.average(x,axis=0,weights=weights);my=float(np.average(y,weights=weights))
    a=(x-mx)*np.sqrt(weights[:,None]);b=(y-my)*np.sqrt(weights)
    w=a.T@np.linalg.solve(a@a.T+penalty*np.eye(len(y)),b)
    return w,float(my-mx@w)

def choose(x,y):
    trials=[]
    for penalty in [.001,.01,.1,1.,10.]:
        scores=[]
        for i in range(len(y)):
            keep=np.arange(len(y))!=i;w,b=fit(x[keep],y[keep],penalty);scores.append(float(x[i]@w+b))
        scores=np.array(scores);fn=int(((scores<0)&(y>0)).sum());fp=int(((scores>=0)&(y<0)).sum())
        trials.append(dict(penalty=penalty,screw_misses=fn,normal_false_positives=fp,balanced_error=.5*(fn/(y>0).sum()+fp/(y<0).sum())))
    best=min(trials,key=lambda z:(z['balanced_error'],-z['penalty']))
    return best['penalty'],trials

def main():
    import onnxruntime as ort
    OUT.mkdir(exist_ok=True)
    plan=read(PRIOR/'plan.json');m=read(ROOT/'models/dino-paired-47-20261103/manifest.json')
    ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids']
    x=np.array(m['example_bank']['screw']['embeddings']+m['example_bank']['normal']['embeddings'],dtype='float64')
    y=np.r_[np.ones(47),-np.ones(65)]
    held={z['key'] for z in plan['cases']};known_overlap=[i for i,name in enumerate(ids) if name.removesuffix('.png') in held]
    protocols={};models={}
    for label,include in [('all_47_65',np.ones(len(y),bool)),('exclude_identified_test_examples',np.array([i not in known_overlap for i in range(len(y))]))]:
        penalty,trials=choose(x[include],y[include]);models[label]=fit(x[include],y[include],penalty)
        protocols[label]=dict(penalty=penalty,trials=trials,screw_examples=int((y[include]>0).sum()),normal_examples=int((y[include]<0).sum()))
        print(label,'penalty',penalty,'example LOO',trials,flush=True)
    save(OUT/'training.json',dict(protocols=protocols,known_test_overlap_ids=[ids[i] for i in known_overlap],
         caveat='Other same-source or montage overlap cannot be ruled out; same 17 development cases, not independent accuracy.',selection='Regularization selected by balanced leave-one-out error on example bank only; threshold fixed at zero.'))
    # Freeze the fitted parameters before reading test vectors or evaluating results.
    np.savez(OUT/'classifiers.npz',**{label+'_'+k:a for label,(w,b) in models.items() for k,a in [('w',w),('b',b)]})
    o=ort.SessionOptions();o.intra_op_num_threads=4;session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=o,providers=['CPUExecutionProvider'])
    cachefile=OUT/'test-vectors.npz';vectors=dict(np.load(cachefile)) if cachefile.exists() else {}
    results=[]
    for n,z in enumerate(plan['cases'],1):
        result=dict(number=n,key=z['key'],expected=z['expected'],variants={})
        for variant in ['original','focused','soft_background']:
            pair=[]
            for side in ['target','reference']:
                f=PRIOR/'images'/f'{n}-dino-{side}.png' if variant=='original' else FOCUS/'images'/f'{n}-{variant}-{side}.png'
                key=hashlib.sha256(f.read_bytes()).hexdigest()
                if key not in vectors:vectors[key]=embedding(m,session,np.asarray(Image.open(f).convert('L'),dtype='float32')/255)
                pair.append(vectors[key])
            result['variants'][variant]={}
            for label,(w,b) in models.items():
                t,r=[float(v@w+b) for v in pair]
                result['variants'][variant][label]=dict(target_score=t,reference_score=r,target_screw=t>=0,reference_screw=r>=0,paired_keep=t>=0 and r<0)
        results.append(result);print(n,z['category'],{k:{p:(round(v['target_score'],3),round(v['reference_score'],3),v['paired_keep']) for p,v in vs.items()} for k,vs in result['variants'].items()},flush=True)
    np.savez(cachefile,**vectors);save(OUT/'results.json',results)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],original_plan_sha256=hashlib.sha256((PRIOR/'plan.json').read_bytes()).hexdigest(),formal_changes=False))
if __name__=='__main__':main()
