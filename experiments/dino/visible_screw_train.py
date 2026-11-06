"""Training-only exposed-part bank and fixed thresholds; no heldout score tuning."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np,cv2
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-visible-screw-20261106';OUT.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from visible_screw_geometry import proposals,part_image
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image,features,example_features
from blackblock_ablation import score
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    rows=[];positive=[];views={};(OUT/'part-examples').mkdir(exist_ok=True)
    for photo in ('128','131','132'):
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')];parts=proposals(ref,tar)
        selected=[p for p in parts if p['box'][0]<=732<p['box'][0]+p['box'][2] and p['box'][1]<=448<p['box'][1]+p['box'][3]]
        assert len(selected)==1,(photo,[p['box'] for p in selected]);b=selected[0]['box'];im=part_image(tar,b);positive.append(example_features(snap.manifest,snap.session,im));Image.fromarray(np.uint8(im*255)).save(OUT/'part-examples'/f'positive-{photo}.png');print('PART POSITIVE',photo,b,flush=True)
        for i,p in enumerate(parts):
            p={k:v for k,v in p.items() if k!='mask'};r=dict(p,photo=photo,id=i,key=f'{photo}-part-{i}',known_B=p['box']==b,features={});views[r['key']]={}
            for side,a0 in [('reference',ref),('target',tar)]:
                crop=part_image(a0,p['box']);view=adjusted_image(snap.manifest,crop);r['features'][side]=features(snap.manifest,snap.session,view);views[r['key']][side]=crop
            rows.append(r)
    bank=np.concatenate([snap.feature_bank[:47],np.asarray(positive),snap.feature_bank[47:]])
    for r in rows:r['initial_pair']={s:score(v,bank,50) for s,v in r['features'].items()}
    ranked=sorted(rows,key=lambda r:-r['initial_pair']['reference']['margin']);negatives=[];boxes=[]
    for r in ranked:
        x,y,w,h=r['box']
        if any(abs(x-X)<15 and abs(y-Y)<15 for X,Y in boxes):continue
        if views[r['key']]['reference'].std()<.03:continue
        negatives.append(r);boxes.append((x,y))
        if len(negatives)==12:break
    extra=[]
    for r in negatives:
        im=views[r['key']]['reference'];extra.append(example_features(snap.manifest,snap.session,im));Image.fromarray(np.uint8(im*255)).save(OUT/'part-examples'/f'negative-{r["key"]}.png')
    hard=np.concatenate([bank,np.asarray(extra)]);np.savez_compressed(OUT/'visible-part-bank.npz',bank=hard)
    for r in rows:
        r['pair']={s:score(v,hard,50) for s,v in r['features'].items()};r.pop('features')
        if r['known_B']:print('B SCORE',r['photo'],r['pair'],flush=True)
    save(OUT/'training-part-scores.json',rows);save(OUT/'part-bank-plan.json',dict(positive_photos=['128','131','132'],negative_examples=[dict(key=r['key'],box=r['box'],side='reference',authority='Golden reference normal patch, automatically mined') for r in negatives],original_47_and_65_retained=True,black_block_positive_examples=0,positives='Only image-derived exposed B rectangles, no occluder pixels or padding context',model_fingerprint=snap.identity))
    for t in (0,.05,.1,.15,.2,.25,.3):
        keep=[r for r in rows if r['pair']['target']['margin']>=t and r['pair']['reference']['margin']<0];print('THRESHOLD',t,'B',sum(r['known_B'] for r in keep),'other',[(r['key'],r['box'],round(r['pair']['target']['margin'],3)) for r in keep if not r['known_B']],flush=True)
if __name__=='__main__':main()
