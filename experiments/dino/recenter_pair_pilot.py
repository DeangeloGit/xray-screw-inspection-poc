"""Offline crop-stability test, using all 17 frozen pairs and identical rules.

The map is calculated from full aligned images, independent of candidate jitter.
Only generic connected components determine coordinates; no hard-coded screw box.
"""
import sys,hashlib
from pathlib import Path
import numpy as np,cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.local_added_object_pilot import read,save,OUT as PRIOR
from dino_adapter import embedding,input_image,classify_vector
OUT=ROOT/'workspace/dino-recenter-pair-20261103'
PREVIOUS=ROOT/'workspace/dino-multiscale-pair-20261103'
OFFSETS=[(0,0),(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,-2),(-2,2),(2,2),(-4,0),(4,0),(0,-4),(0,4)]
RULES=dict(threshold=.08,smoothing_sigma=.6,background_sigma=12,modes=['raw_difference','local_brightness_removed'],offsets=OFFSETS,
    selection='connected component with largest overlap with the shifted original candidate; tie by component number',
    crop='square using connected-component longer side and center; same original-image coordinates for both views; no extra padding, masking or image shifting',
    success='target screw AND reference non-screw; no review class; zero remains classification threshold',
    test_note='Development test on same known 17 cases; shifts on same images are not new independent samples; no new examples.')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    import onnxruntime as ort
    OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
    rulefile=OUT/'rules.json'
    if rulefile.exists():assert read(rulefile)==read_json_rules()
    else:save(rulefile,RULES)
    plan=read(PRIOR/'plan.json');oldboxes=read(ROOT/'workspace/focused-object-pilot-20261103/results.json');model=ROOT/'models/dino-paired-47-20261103'
    protected=[p for p in model.rglob('*') if p.is_file()]+[ROOT/'models/active.json']+[ROOT/f for f in ['detector.py','dino_adapter.py','library.py','acquisition.py','static/user.js']]
    for z in plan['cases']:protected.extend(Path(z['source'])/f for f in ['reference.png','aligned.png','result.json'])
    hashes={str(p):digest(p) for p in protected};save(OUT/'preservation-before.json',hashes)
    save(OUT/'plan.json',dict(keys=[z['key'] for z in plan['cases']],previous_plan_sha256=digest(PRIOR/'plan.json'),offsets=OFFSETS))
    m=read(model/'manifest.json');options=ort.SessionOptions();options.intra_op_num_threads=4
    session=ort.InferenceSession(str(model/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    vectors={}
    # Reuse only exact previously computed 224x224 RGB inputs.
    for f in [PREVIOUS/'features.npz',OUT/'features.npz']:
        if f.exists():vectors.update(dict(np.load(f)))
    results=[]
    def classify_pair(ref,tar,box,name=None):
        answer={};x0,y0,side=box
        if x0<0 or y0<0 or x0+side>ref.width or y0+side>ref.height:return dict(valid=False,reason='crop_outside_image',box=box)
        for side_name,im in [('reference',ref),('target',tar)]:
            a=np.asarray(im.crop((x0,y0,x0+side,y0+side)),dtype='float32')/255;inp=input_image(m,a);key=hashlib.sha256(inp.tobytes()).hexdigest()
            if key not in vectors:vectors[key]=embedding(m,session,a)
            c=classify_vector(m,vectors[key]);answer[side_name]=dict(screw=c['label']=='screw',margin=c['screw_margin'],input_sha256=key)
            if name:inp.save(OUT/'images'/f'{name}-{side_name}.png')
        return dict(valid=True,box=box,**answer,paired_keep=answer['target']['screw'] and not answer['reference']['screw'])
    for n,(z,old) in enumerate(zip(plan['cases'],oldboxes),1):
        assert z['key']==old['key'];ref=Image.open(Path(z['source'])/'reference.png').convert('L');tar=Image.open(Path(z['source'])/'aligned.png').convert('L')
        r,t=[np.asarray(im,dtype='float32')/255 for im in [ref,tar]];delta=cv2.GaussianBlur(r-t,(3,3),RULES['smoothing_sigma'])
        maps={'raw_difference':delta,'local_brightness_removed':delta-cv2.GaussianBlur(delta,(0,0),RULES['background_sigma'])}
        components={k:cv2.connectedComponentsWithStats((v>RULES['threshold']).astype('uint8')) for k,v in maps.items()}
        x,y,w,h=(z['c'][k] for k in ['x','y','w','h']);ox,oy,ow,oh=old['object_box'];oldside=max(ow,oh);oldx,oldy=round(ox+ow/2-oldside/2),round(oy+oh/2-oldside/2)
        rec=dict(number=n,key=z['key'],category=z['category'],expected=z['expected'],trials=[])
        for dx,dy in OFFSETS:
            baseline=classify_pair(ref,tar,[oldx+dx,oldy+dy,oldside],f'{n}-before-{dx}-{dy}' if n<=2 else None)
            trial=dict(dx=dx,dy=dy,before=baseline,modes={})
            for mode,(_,labels,stats,_) in components.items():
                ids,counts=np.unique(labels[y+dy:y+h+dy,x+dx:x+w+dx],return_counts=True);hits=[(int(count),int(i)) for i,count in zip(ids,counts) if i]
                if not hits:trial['modes'][mode]=dict(valid=False,reason='no_component_overlapping_candidate');continue
                component=max(hits)[1];bx,by,bw,bh,area=stats[component].tolist();size=max(bw,bh);box=[round(bx+bw/2-size/2),round(by+bh/2-size/2),size]
                answer=classify_pair(ref,tar,box,f'{n}-{mode}-{dx}-{dy}' if n<=2 or (dx==0 and dy==0) else None)
                trial['modes'][mode]=dict(**answer,component=component,object_box=[bx,by,bw,bh],area=area)
            rec['trials'].append(trial)
        results.append(rec);save(OUT/'results.json',results);np.savez(OUT/'features.npz',**vectors)
        print(n,z['category'],'before',sum(t['before'].get('paired_keep',False) for t in rec['trials']),{mode:dict(kept=sum(t['modes'][mode].get('paired_keep',False) for t in rec['trials']),invalid=sum(not t['modes'][mode]['valid'] for t in rec['trials']),boxes=len({tuple(t['modes'][mode].get('box',[])) for t in rec['trials']})) for mode in RULES['modes']},flush=True)
    changed=[p for p,v in hashes.items() if digest(Path(p))!=v];assert not changed,changed
    save(OUT/'preservation.json',dict(protected_files=len(hashes),unchanged=True,formal_changes=False))
def read_json_rules():
    import json
    return json.loads(json.dumps(RULES))
if __name__=='__main__':main()
