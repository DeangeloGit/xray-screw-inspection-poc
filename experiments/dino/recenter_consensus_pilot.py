"""Stabilize geometry with nine local contour estimates; never vote on AI labels."""
import sys,json,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.recenter_local_pilot import extract,PRIOR,OFFSETS,read,save,digest
from dino_adapter import embedding,input_image,classify_vector
OUT=ROOT/'workspace/dino-recenter-consensus-20261103'
RULES=dict(test_offsets=OFFSETS,geometry_offsets=[(dx,dy) for dx in [-2,0,2] for dy in [-2,0,2]],
          merge='median of component left,top,right,bottom; valid contours >=5 of 9; no AI score used to select crop',
          fallback='original padded12 paired crop if fewer than five valid component estimates',
          classifier='unchanged DINO 47 screw +65 normal, top3, threshold0; target screw AND reference non-screw',formal_changes=False)
def main():
    import onnxruntime as ort
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True);p=OUT/'rules.json'
    if p.exists():assert read(p)==json.loads(json.dumps(RULES))
    else:save(p,RULES)
    plan=read(PRIOR/'plan.json');m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');opt=ort.SessionOptions();opt.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=opt,providers=['CPUExecutionProvider']);cache={}
    for f in [ROOT/'workspace/dino-recenter-local-20261103/features.npz',OUT/'features.npz']:
        if f.exists():cache.update(dict(np.load(f)))
    results=[]
    for n,z in enumerate(plan['cases'],1):
        images=[Image.open(Path(z['source'])/f).convert('L') for f in ['reference.png','aligned.png']];arrays=[np.asarray(im,dtype='float32')/255 for im in images];estimates={};rec=dict(number=n,key=z['key'],category=z['category'],expected=z['expected'],trials=[])
        for dx,dy in OFFSETS:
            votes=[]
            for qx,qy in RULES['geometry_offsets']:
                offset=(dx+qx,dy+qy)
                if offset not in estimates:estimates[offset]=extract(*arrays,dict(z['c'],x=z['c']['x']+offset[0],y=z['c']['y']+offset[1]))
                ex=estimates[offset]
                if ex['valid']:
                    x,y,w,h=ex['object_box'];votes.append([x,y,x+w,y+h])
            if len(votes)>=5:
                left,top,right,bottom=np.median(votes,axis=0);side=int(round(max(right-left,bottom-top)));x0,y0=round((left+right-side)/2),round((top+bottom-side)/2);box=(x0,y0,x0+side,y0+side);method='median_geometry'
            else:
                c=z['c'];box=(c['x']+dx-12,c['y']+dy-12,c['x']+c['w']+dx+12,c['y']+c['h']+dy+12);method='original_crop_fallback'
            pred={}
            for label,im in zip(['reference','target'],images):
                crop=np.asarray(im.crop(box),dtype='float32')/255;inp=input_image(m,crop);key=hashlib.sha256(inp.tobytes()).hexdigest()
                if key not in cache:cache[key]=embedding(m,session,crop)
                c=classify_vector(m,cache[key]);pred[label]=dict(screw=c['label']=='screw',margin=c['screw_margin'],input_sha256=key)
                inp.save(OUT/'images'/f'{n}-{dx}-{dy}-{label}.png')
            rec['trials'].append(dict(dx=dx,dy=dy,method=method,crop_box=list(box),geometry_estimates=votes,**pred,paired_keep=pred['target']['screw'] and not pred['reference']['screw']))
        results.append(rec);save(OUT/'results.json',results);np.savez(OUT/'features.npz',**cache)
        print(n,z['category'],'kept',sum(t['paired_keep'] for t in rec['trials']),'boxes',len({tuple(t['crop_box']) for t in rec['trials']}),'alert offsets',[(t['dx'],t['dy']) for t in rec['trials'] if t['paired_keep']],flush=True)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],previous_plan_sha256=digest(PRIOR/'plan.json')))
if __name__=='__main__':main()
