"""Recompute the previous successful local contour after every proposal shift.
This tests the actual extraction pipeline, not cached boxes or a forced decision.
"""
import sys,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.recenter_pair_pilot import PRIOR,OFFSETS,read,save,digest
from experiments.dino.local_added_object_pilot import compare
from dino_adapter import embedding,input_image,classify_vector
OUT=ROOT/'workspace/dino-recenter-local-20261103'
def extract(ref,tar,c):
    x,y,w,h=(c[k] for k in ['x','y','w','h']);metrics,*_=compare(ref,tar,c);dx,dy=metrics['dx'],metrics['dy'];e=32
    x0,y0=max(e,x-e),max(e,y-e);x1,y1=min(ref.shape[1]-e,x+w+e),min(ref.shape[0]-e,y+h+e)
    a=tar[y0:y1,x0:x1];b=ref[y0+dy:y1+dy,x0+dx:x1+dx];fitted=np.clip(metrics['gain']*b+metrics['offset'],0,1)
    delta=cv2.GaussianBlur(fitted-a,(3,3),.6);_,labels,stats,_=cv2.connectedComponentsWithStats((delta>.08).astype('uint8'))
    ids,counts=np.unique(labels[y-y0:y+h-y0,x-x0:x+w-x0],return_counts=True);hits=[(int(count),int(i)) for i,count in zip(ids,counts) if i]
    if not hits:return dict(valid=False,reason='no_component')
    selected=max(hits)[1];xx,yy,ww,hh,area=stats[selected].tolist();bx,by=x0+xx,y0+yy;side=max(ww,hh)
    return dict(valid=True,object_box=[bx,by,ww,hh],box=[round(bx+ww/2-side/2),round(by+hh/2-side/2),side],area=area,metrics=metrics)
def main():
    import onnxruntime as ort,json
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    rules=dict(offsets=OFFSETS,method='Recompute previous local exposure/translation-assisted contour with perturbed proposal; crop SAME coordinates from original aligned reference and target; no local translation or exposure applied to DINO images',threshold=.08,padding=0,fallback='original padded-12 paired crop if contour unavailable',formal_changes=False)
    p=OUT/'rules.json'
    if p.exists():assert read(p)==json.loads(json.dumps(rules))
    else:save(p,rules)
    plan=read(PRIOR/'plan.json');m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');opts=ort.SessionOptions();opts.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    cache={}
    for f in [ROOT/'workspace/dino-multiscale-pair-20261103/features.npz',ROOT/'workspace/dino-recenter-pair-20261103/features.npz',OUT/'features.npz']:
        if f.exists():cache.update(dict(np.load(f)))
    results=[]
    for n,z in enumerate(plan['cases'],1):
        images=[Image.open(Path(z['source'])/f).convert('L') for f in ['reference.png','aligned.png']];arrays=[np.asarray(im,dtype='float32')/255 for im in images];rec=dict(number=n,key=z['key'],category=z['category'],expected=z['expected'],trials=[])
        for dx,dy in OFFSETS:
            c=dict(z['c'],x=z['c']['x']+dx,y=z['c']['y']+dy);ex=extract(*arrays,c)
            if ex['valid']:
                x,y,side=ex['box'];cropbox=(x,y,x+side,y+side);method='recentered'
            else:cropbox=(c['x']-12,c['y']-12,c['x']+c['w']+12,c['y']+c['h']+12);method='original_crop_fallback'
            pred={}
            for label,im in zip(['reference','target'],images):
                crop=np.asarray(im.crop(cropbox),dtype='float32')/255;inp=input_image(m,crop);key=hashlib.sha256(inp.tobytes()).hexdigest()
                if key not in cache:cache[key]=embedding(m,session,crop)
                ans=classify_vector(m,cache[key]);pred[label]=dict(screw=ans['label']=='screw',margin=ans['screw_margin'],input_sha256=key)
                if n<=2 or (dx,dy)==(0,0):inp.save(OUT/'images'/f'{n}-{dx}-{dy}-{label}.png')
            rec['trials'].append(dict(dx=dx,dy=dy,extraction=ex,method=method,crop_box=list(cropbox),**pred,paired_keep=pred['target']['screw'] and not pred['reference']['screw']))
        results.append(rec);save(OUT/'results.json',results);np.savez(OUT/'features.npz',**cache)
        print(n,z['category'],'kept',sum(t['paired_keep'] for t in rec['trials']),'boxes',len({tuple(t['crop_box']) for t in rec['trials']}),'failed offsets',[(t['dx'],t['dy']) for t in rec['trials'] if not t['paired_keep']] if n<=2 else '',flush=True)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],prior_hash=digest(PRIOR/'plan.json')))
if __name__=='__main__':main()
