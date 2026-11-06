"""Fixed-query experiment: change only DINO example contents, not query crops."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-bank-only-20261106';AUDIT=ROOT/'workspace/dino-4r-example-audit-20261106';PRIOR=ROOT/'workspace/dino-4r-crossbatch-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image,features,example_features
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def score(v,bank,n=47):
    sims=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
    margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in sims]
    return dict(margin=sum(margins)/2,whole=margins[0],local=margins[1],positive_neighbors=[(np.argsort(s[:n])[-3:][::-1]+1).tolist() for s in sims],normal_neighbors=[(np.argsort(s[n:])[-3:][::-1]+1).tolist() for s in sims])
def main():
    import cv2
    cv2.setNumThreads(4);OUT.mkdir(exist_ok=True);(OUT/'examples').mkdir(exist_ok=True)
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    model=ROOT/'models'/snap.requested;ex=read(model/'examples.json');base=snap.feature_bank;clean=base.copy();review=[];background={}
    # Assistant visual outline review, never re-label these true screw examples.
    rectangles={5:[11,11,43,41],7:[9,13,37,46],20:[13,15,42,49]}
    for n,rect in rectangles.items():
        key=f'screw-p1-{n}.png';p=model/'examples'/ex[key]['file'];im=Image.open(p).convert('L');a=np.asarray(im,np.float32)/255;x,y,X,Y=rect;object_crop=a[y:Y,x:X]
        clean[n-1]=example_features(snap.manifest,snap.session,object_crop)
        # Synthetic diagnostic only: erase the screw rectangle, retain original
        # background canvas. Do not put this synthetic control into any bank.
        bg=a.copy();bg[y:Y,x:X]=1.;background[n]=example_features(snap.manifest,snap.session,bg)
        for tag,array in [('original',a),('object',object_crop),('background-control',bg)]:adjusted_image(snap.manifest,array).save(OUT/'examples'/f'S{n:02}-{tag}.png')
        review.append(dict(index=n,id=key,source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),object_rectangle=rect,authority='assistant visual review; same positive label; background-control synthetic and not used as example'))
    r=read(PRIOR/'runs/ng-128/result.json');c=next(c for c in r['filtered_candidates'] if c['id']==22);x,y,w,h=c['classification']['canonical_object']['box'];tar=np.asarray(Image.open(PRIOR/'runs/ng-128/aligned.png').convert('L'),np.float32)/255
    normal=tar[y-12:y+h+12,x-12:x+w+12];normalbank=example_features(snap.manifest,snap.session,normal)[None];adjusted_image(snap.manifest,normal).save(OUT/'examples/N66-confirmed-22.png')
    keep=[i for i in range(47) if i not in (4,6,19)]+list(range(47,112))
    banks={'original':(base,47),'normal_add1':(np.concatenate([base,normalbank]),47),'positive_clean3':(clean,47),'clean3_normal_add1':(np.concatenate([clean,normalbank]),47),'drop3_diagnostic':(base[keep],44)}
    for name,(bank,n) in banks.items():np.savez_compressed(OUT/f'{name}-bank.npz',bank=bank,n=n)
    save(OUT/'example-review.json',dict(positive_examples=review,normal_added=dict(source='ng-128 #22',human_label='normal',crop_box=[x-12,y-12,w+24,h+24],counted_examples=1,augmentations=8),query='fixed original center crop +12, bit-identical feature SHA for all bank arms',removed_examples_diagnostic_only=[5,7,20],production_modified=False))
    scores=read(AUDIT/'all-crop-bank-scores.json');cases={c['key']:c for c in read(PRIOR/'cases.json')};rows=[];controls=[]
    for photo in map(str,range(128,138)):
        cache=np.load(AUDIT/'all-features'/f'{photo}.npz')
        for z in scores:
            if z['photo']!=photo:continue
            pair={side:cache[z['variants']['center-12-old'][side]['input_sha256']] for side in ('reference','target')}
            arms={}
            for name,(bank,n) in banks.items():
                result={side:score(v,bank,n) for side,v in pair.items()};result['keep']=result['target']['margin']>=0 and result['reference']['margin']<0;arms[name]=result
            row=dict(key=f'ng-{photo}-{z["id"]}',photo=photo,id=z['id'],box=z['box'],input_sha256={s:z['variants']['center-12-old'][s]['input_sha256'] for s in pair},answers=cases[f'ng-{photo}-{z["id"]}']['answers'],arms=arms);rows.append(row)
            if photo=='128' and z['id'] in (22,40):
                print('PAIR',z['id'],{k:round(v['target']['margin'],5) for k,v in arms.items()},flush=True)
                for n in rectangles:
                    for name,bank in [('original',base[n-1]),('object',clean[n-1]),('background',background[n])]:
                        controls.append(dict(candidate=z['id'],positive=n,variant=name,whole=float((bank[:,0]@pair['target'][0]).max()),local=float(bank[0,1]@pair['target'][1])))
    summary=[]
    original_hits={(r['photo'],a) for r in rows if r['arms']['original']['keep'] for a in r['answers']}
    for name in banks:
        hits={(r['photo'],a) for r in rows if r['arms'][name]['keep'] for a in r['answers']};row=dict(arm=name,raw_fixed_crop_hits=len(hits),lost_raw_hits=sorted(original_hits-hits),raw_unmatched=sum(r['arms'][name]['keep'] and not r['answers'] for r in rows),changed=[r['key'] for r in rows if r['arms'][name]['keep']!=r['arms']['original']['keep']]);summary.append(row);print('RAW',name,'hits',len(hits),'lost',len(original_hits-hits),'unmatched',row['raw_unmatched'],flush=True)
    save(OUT/'fixed-query-scores.json',rows);save(OUT/'fixed-query-summary.json',summary);save(OUT/'background-controls.json',controls)
if __name__=='__main__':main()
