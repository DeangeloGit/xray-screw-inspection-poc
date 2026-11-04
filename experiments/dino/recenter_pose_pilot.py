"""Second centering trial: remove one-pixel bridges, optionally orient long parts.
All rules apply equally to the frozen screw and normal cases; no manual coordinates.
"""
import sys,hashlib,math
from pathlib import Path
import numpy as np,cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.recenter_pair_pilot import PRIOR,OFFSETS,read,save,digest
from dino_adapter import input_image,embedding,classify_vector
OUT=ROOT/'workspace/dino-recenter-pose-20261103'
RULES=dict(threshold=.08,background_sigma=12,opening='3x3 ellipse, one pass',extra_padding=2,elongation_ratio=2.5,
    offsets=OFFSETS,modes=['opened_center','opened_upright'],fallback='If no component overlaps the perturbed proposal, classify its original padded-12 paired crops; no review or forced exclusion.',
    selection='max overlap with perturbed proposal; components from complete aligned image pair, not saved successful boxes',
    classifier='unchanged DINO 47+65, top3 each, margin 0 on both sides')
def main():
    import json,onnxruntime as ort
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    p=OUT/'rules.json'
    if p.exists():assert read(p)==json.loads(json.dumps(RULES))
    else:save(p,RULES)
    plan=read(PRIOR/'plan.json');m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');opts=ort.SessionOptions();opts.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    cache={};results=[]
    for f in [ROOT/'workspace/dino-recenter-pair-20261103/features.npz',OUT/'features.npz']:
        if f.exists():cache.update(dict(np.load(f)))
    def infer(images,name):
        sides={}
        for side,im in zip(['reference','target'],images):
            inp=input_image(m,np.asarray(im,dtype='float32')/255);key=hashlib.sha256(inp.tobytes()).hexdigest()
            if key not in cache:cache[key]=embedding(m,session,np.asarray(im,dtype='float32')/255)
            c=classify_vector(m,cache[key]);sides[side]=dict(screw=c['label']=='screw',margin=c['screw_margin'],input_sha256=key)
            inp.save(OUT/'images'/f'{name}-{side}.png')
        return dict(**sides,paired_keep=sides['target']['screw'] and not sides['reference']['screw'])
    for n,z in enumerate(plan['cases'],1):
        images=[Image.open(Path(z['source'])/f).convert('L') for f in ['reference.png','aligned.png']];arrays=[np.asarray(im,dtype='float32')/255 for im in images]
        delta=cv2.GaussianBlur(arrays[0]-arrays[1],(3,3),.6);delta-=cv2.GaussianBlur(delta,(0,0),12)
        binary=cv2.morphologyEx((delta>.08).astype('uint8'),cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
        _,labels,stats,_=cv2.connectedComponentsWithStats(binary);computed={};rec=dict(number=n,key=z['key'],category=z['category'],expected=z['expected'],trials=[])
        x,y,w,h=(z['c'][k] for k in ['x','y','w','h'])
        for dx,dy in OFFSETS:
            ids,counts=np.unique(labels[y+dy:y+h+dy,x+dx:x+w+dx],return_counts=True);hits=[(int(count),int(i)) for i,count in zip(ids,counts) if i];trial=dict(dx=dx,dy=dy,modes={})
            if not hits:
                box=(x+dx-12,y+dy-12,x+w+dx+12,y+h+dy+12);prediction=infer([im.crop(box) for im in images],f'{n}-fallback-{dx}-{dy}')
                for mode in RULES['modes']:trial['modes'][mode]=dict(**prediction,method='original_crop_fallback',box=list(box))
            else:
                component=max(hits)[1]
                if component not in computed:
                    bx,by,bw,bh,area=stats[component].tolist();ys,xs=np.where(labels[by:by+bh,bx:bx+bw]==component);pts=np.c_[xs+bx,ys+by].astype('float64');center=pts.mean(axis=0)
                    vals,vecs=np.linalg.eigh(np.cov(pts.T)) if len(pts)>2 else (np.array([1,1]),np.eye(2));ratio=float(vals[-1]/max(vals[0],.001));v=vecs[:,-1]
                    if v[1]<0:v=-v
                    angle=math.degrees(math.atan2(v[1],v[0]))-90 if ratio>=2.5 else 0.
                    computed[component]={}
                    for mode in RULES['modes']:
                        degrees=angle if mode=='opened_upright' else 0.;matrix=cv2.getRotationMatrix2D(tuple(center),degrees,1.);q=pts@matrix[:,:2].T+matrix[:,2];lo=np.floor(q.min(axis=0));hi=np.ceil(q.max(axis=0));cw,ch=(hi-lo+1);side=int(max(cw,ch))+4;cx,cy=(lo+hi)/2;left,top=round(cx-(side-1)/2),round(cy-(side-1)/2)
                        # Directly sample the rotated crop from full original images.
                        matrix[:,2]-=np.array([left,top]);crops=[Image.fromarray(cv2.warpAffine(np.asarray(im),matrix,(side,side),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)) for im in images]
                        name=f'{n}-{mode}-component-{component}';pred=infer(crops,name);computed[component][mode]=dict(**pred,method=mode,component=component,object_box=[bx,by,bw,bh],rotation_degrees=degrees,elongation=ratio,crop_side=side,image_prefix=name)
                trial['modes']=computed[component]
            rec['trials'].append(trial)
        results.append(rec);save(OUT/'results.json',results);np.savez(OUT/'features.npz',**cache)
        print(n,z['category'],{mode:dict(kept=sum(t['modes'][mode]['paired_keep'] for t in rec['trials']),fallback=sum(t['modes'][mode]['method']=='original_crop_fallback' for t in rec['trials']),base=(round(rec['trials'][0]['modes'][mode]['target']['margin'],4),round(rec['trials'][0]['modes'][mode]['reference']['margin'],4))) for mode in RULES['modes']},flush=True)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],prior_hash=digest(PRIOR/'plan.json')))
if __name__=='__main__':main()
