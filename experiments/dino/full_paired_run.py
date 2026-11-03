"""Frozen 47+65 target/reference evaluation on all saved difference candidates."""
import sys,json,hashlib,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import onnxruntime as ort
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from dino_adapter import input_image,embedding
BASE=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103'
OUT=ROOT/'workspace/windows-check/diagnostics/dino-47-paired-full-20261103'
MODEL='dino-examples-176c7281352c4e74'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def prediction(m,v):
    e={}
    for label in ('screw','normal'):
        b=m['example_bank'][label];scores=np.asarray(b['embeddings'],np.float32)@v;ids=np.argsort(scores)[-3:][::-1]
        e[label]=dict(similarity=float(scores[ids].mean()),neighbors=[b['ids'][i] for i in ids])
    margin=e['screw']['similarity']-e['normal']['similarity']
    return dict(screw=margin>=0,margin=margin,evidence=e)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    m=read(ROOT/'models'/MODEL/'manifest.json');old=read(ROOT/'models/dino-examples-a3b8c97aa539/manifest.json');rows=read(BASE/'report-rows.json')
    assert len(m['example_bank']['screw']['ids'])==47 and len(m['example_bank']['normal']['ids'])==65
    assert m['example_bank']['normal']==old['example_bank']['normal']
    assert m['example_bank']['screw']['ids'][:31]==old['example_bank']['screw']['ids']
    inputs={};cases=[];hashes={str(ROOT/'models/active.json'):digest(ROOT/'models/active.json')}
    for file in [ROOT/'models'/MODEL/'manifest.json',ROOT/'models'/MODEL/'model.onnx',ROOT/'dino_adapter.py',BASE/'results.json']:hashes[str(file)]=digest(file)
    for r in rows:
        p=BASE/'photos'/r['sha256'];res=read(p/'result.json');hashes[str(p/'result.json')]=digest(p/'result.json')
        cc=res['candidates']+res['filtered_candidates']
        cs=[dict(key=f'{r["sha256"]}-{c["id"]}',sha=r['sha256'],name=r['relative'],machine=r['machine'],label=r['label'],id=c['id'],c=c,
                 old_keep=c['classification']['action']!='discard',known=any(c['id'] in k['retained_ids']+k['removed_ids'] for k in r.get('known_checks',[]))) for c in cc]
        for side,file in [('target','aligned.png'),('reference','reference.png')]:
            hashes[str(p/file)]=digest(p/file)
            with Image.open(p/file) as image:
                im=image.convert('L')
                for z in cs:
                    c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));crop=im.crop((max(0,x-12),max(0,y-12),min(im.width,x+w+12),min(im.height,y+h+12)))
                    a=np.asarray(input_image(m,np.asarray(crop,np.float32)/255))[:,:,0].copy();key=hashlib.sha256(a.tobytes()).hexdigest();z[side+'_input']=key;inputs[key]=a
        cases+=cs
    assert len(cases)==2793
    plan=dict(model=MODEL,hashes=hashes,images=len(rows),reference_images=sum(r['is_reference'] for r in rows),candidates=len(cases),unique_inputs=len(inputs),
        rules=dict(old='31 screw + 65 normal; target only',new='47 screw + 65 normal; target only',paired='47+65: keep only target screw AND reference non-screw; both screw => discard'),
        caveat='Development evaluation: new user montage may overlap this dataset; source photos of the 16 montage crops are not mapped. No independent accuracy claim. Reuses all fixed difference candidates; no detection rerun.',code_hash=digest(Path(__file__)))
    planpath=OUT/'plan.json'
    if planpath.exists():assert read(planpath)==plan,'Frozen inputs changed; use a new output directory'
    else:planpath.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    cachefile=OUT/'features.npz';vectors={}
    if cachefile.exists():
        with np.load(cachefile) as data:vectors={k:data[k] for k in data.files}
    pending=[k for k in inputs if k not in vectors]
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(ROOT/'models'/MODEL/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    start=time.monotonic();print('START',len(cases),'candidates;',len(inputs),'unique inputs;',len(pending),'pending',flush=True)
    def calculate(k):return embedding(m,session,inputs[k].astype(np.float32)/255)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(calculate,k):k for k in pending}
        for i,f in enumerate(as_completed(futures),1):
            vectors[futures[f]]=f.result()
            if i%100==0:
                np.savez_compressed(cachefile,**vectors);print('FEATURES',i,'/',len(pending),'seconds',round(time.monotonic()-start),flush=True)
    np.savez_compressed(cachefile,**vectors)
    maxerror=0
    for z in cases:
        target=vectors[z['target_input']];reference=vectors[z['reference_input']]
        oldp=prediction(old,target);error=abs(oldp['margin']-z['c']['classification']['screw_margin']);maxerror=max(maxerror,error)
        assert oldp['screw']==z['old_keep'] and error<1e-5,(z['key'],error)
        z['target']=prediction(m,target);z['reference']=prediction(m,reference);z['new_keep']=z['target']['screw'];z['paired_keep']=z['new_keep'] and not z['reference']['screw']
    (OUT/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(digest(Path(p))==v for p,v in hashes.items())
    summary={}
    for label in ('OK','NG'):
        zs=[z for z in cases if z['label']==label];rs=[r for r in rows if r['label']==label and not r['is_reference']]
        summary[label]=dict(images=len(rs),candidates=len(zs))
        for method in ('old','new','paired'):
            kept=[z for z in zs if z[method+'_keep']];summary[label][method]=dict(kept=len(kept),removed=len(zs)-len(kept),zero_images=sum(not any(z['sha']==r['sha256'] for z in kept) for r in rs))
    summary.update(complete=True,images=len(rows),candidates=len(cases),max_baseline_margin_error=maxerror,active_unchanged=True)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
