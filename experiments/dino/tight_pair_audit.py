"""Audit tight-crop pilot: known example overlap and two-pixel crop sensitivity."""
import sys,copy,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.multiscale_pair_pilot import OUT,PRIOR,read,save
from dino_adapter import embedding,classify_vector
def main():
    import onnxruntime as ort
    plan=read(PRIOR/'plan.json');m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');cache=np.load(OUT/'features.npz')
    keys={z['key'] for z in plan['cases']};clean=copy.deepcopy(m);bank=clean['example_bank']['normal'];keep=[i for i,name in enumerate(bank['ids']) if name.removesuffix('.png') not in keys];removed=[name for i,name in enumerate(bank['ids']) if i not in keep]
    bank['ids']=[bank['ids'][i] for i in keep];bank['embeddings']=[bank['embeddings'][i] for i in keep]
    overlap=[]
    for n,z in enumerate(plan['cases'],1):
        d={}
        for side in ['target','reference']:
            im=Image.open(OUT/'images'/f'{n}-{side}-0.png').convert('RGB');key=hashlib.sha256(im.tobytes()).hexdigest();c=classify_vector(clean,cache[key]);d[side]=dict(screw=c['label']=='screw',margin=c['screw_margin'])
        overlap.append(dict(number=n,key=z['key'],**d,paired_keep=d['target']['screw'] and not d['reference']['screw']))
    save(OUT/'overlap-audit.json',dict(removed_ids=removed,screw_examples=47,normal_examples=len(keep),results=overlap,caveat='Removes identified exact-case normal examples only; other source/montage overlap is unknown. Formal bank unchanged.'))
    print('Overlap audit positives',[(z['target'],z['reference']) for z in overlap[:2]],'normal kept',sum(z['paired_keep'] for z in overlap[2:]),flush=True)
    options=ort.SessionOptions();options.intra_op_num_threads=4;session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    boxes=read(ROOT/'workspace/focused-object-pilot-20261103/results.json');sensitivity=[]
    for n in [1,2]:
        z=plan['cases'][n-1];x,y,w,h=boxes[n-1]['object_box'];cx,cy=x+w/2,y+h/2
        for dx,dy,padding in [(-2,0,0),(2,0,0),(0,-2,0),(0,2,0),(0,0,2),(0,0,4)]:
            size=max(w,h)+padding*2;x0,y0=round(cx-size/2)+dx,round(cy-size/2)+dy;result=dict(number=n,dx=dx,dy=dy,padding=padding)
            for side,f in [('target','aligned.png'),('reference','reference.png')]:
                im=Image.open(Path(z['source'])/f).convert('L');crop=np.asarray(im.crop((x0,y0,x0+size,y0+size)),dtype='float32')/255;c=classify_vector(m,embedding(m,session,crop));result[side]=dict(screw=c['label']=='screw',margin=c['screw_margin'])
            result['paired_keep']=result['target']['screw'] and not result['reference']['screw'];sensitivity.append(result)
            print('Sensitivity',result,flush=True)
    save(OUT/'sensitivity.json',sensitivity)
if __name__=='__main__':main()
