"""Same crop rules on reference/target: five real views, majority decision.
No background masks and no second local registration. All 17 cases are fixed.
"""
import sys,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.local_added_object_pilot import read,save,OUT as PRIOR
from dino_adapter import embedding,classify_vector,input_image
OUT=ROOT/'workspace/dino-multiscale-pair-20261103'
def main():
    import onnxruntime as ort
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    plan=read(PRIOR/'plan.json');boxes=read(ROOT/'workspace/focused-object-pilot-20261103/results.json')
    rules=dict(paddings=[0,8,16,24,32],vote='same 3-of-5 majority independently on target and reference',crop='same square on already-aligned original images, centered on the difference component; no masking, no second registration',formal_changes=False)
    p=OUT/'rules.json'
    if p.exists():assert read(p)==rules
    else:save(p,rules)
    m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');options=ort.SessionOptions();options.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'models/dino-paired-47-20261103/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    results=[];cachefile=OUT/'features.npz';cache=dict(np.load(cachefile)) if cachefile.exists() else {}
    for n,(z,bx) in enumerate(zip(plan['cases'],boxes),1):
        assert bx['key']==z['key'];x,y,w,h=bx['object_box'];cx,cy=x+w/2,y+h/2
        sides={}
        for side,file in [('target','aligned.png'),('reference','reference.png')]:
            im=Image.open(Path(z['source'])/file).convert('L');views=[]
            for padding in rules['paddings']:
                size=max(w,h)+padding*2;x0,y0=round(cx-size/2),round(cy-size/2)
                crop=np.asarray(im.crop((x0,y0,x0+size,y0+size)),dtype='float32')/255
                inp=input_image(m,crop);inp.save(OUT/'images'/f'{n}-{side}-{padding}.png');key=hashlib.sha256(inp.tobytes()).hexdigest()
                if key not in cache:cache[key]=embedding(m,session,crop)
                c=classify_vector(m,cache[key]);views.append(dict(padding=padding,margin=c['screw_margin'],screw=c['label']=='screw',evidence=c['dino_evidence']))
            votes=sum(v['screw'] for v in views);sides[side]=dict(screw=votes>=3,votes=votes,views=views)
        results.append(dict(number=n,key=z['key'],**sides,paired_keep=sides['target']['screw'] and not sides['reference']['screw']))
        print(n,z['category'],[(s,side['votes'],[round(v['margin'],4) for v in side['views']]) for s,side in sides.items()],flush=True)
        np.savez(cachefile,**cache);save(OUT/'results.json',results)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],old_plan_sha256=hashlib.sha256((PRIOR/'plan.json').read_bytes()).hexdigest()))
if __name__=='__main__':main()
