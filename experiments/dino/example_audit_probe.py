"""Isolated 47-example crop audit; no label-dependent runtime decisions."""
import os,sys,json,time,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-example-audit-20261106';BASE=ROOT/'workspace/dino-4r-visible-screw-20261106/v3/final'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image,features,example_features
from blackblock_ablation import score
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def square(a,pad=0):
    h,w=a.shape[:2];s=max(h,w)+2*pad;b=np.ones((s,s),np.float32);y=(s-h)//2;x=(s-w)//2;b[y:y+h,x:x+w]=a;return b
def crop(a,b,pad,letterbox=False):
    x,y,w,h=b;v=a[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]
    return square(v) if letterbox else v
def main():
    import cv2
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    inv=read(OUT/'positive-inventory.json');bankfile=OUT/'letterbox-47-bank.npz'
    if not bankfile.exists():
        pos=[]
        for e in inv:
            im=np.asarray(Image.open(e['path']).convert('L'),np.float32)/255;v=square(im);pos.append(example_features(snap.manifest,snap.session,v));adjusted_image(snap.manifest,v).save(OUT/'bank-review'/f'S{e["index"]:02d}-letterbox.png')
        np.savez_compressed(bankfile,bank=np.concatenate([pos,snap.feature_bank[47:]]))
    banks={'old':snap.feature_bank,'letterbox':np.load(bankfile)['bank']};assert np.array_equal(banks['old'][47:],banks['letterbox'][47:])
    rows=[];allrows='--all' in sys.argv
    for photo in list(map(str,range(128,138)))+(['golden'] if allrows else []):
        dest=OUT/('all-features' if allrows else 'board-probe')/f'{photo}.json'
        if dest.exists():rows+=read(dest);continue
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
        r=read(BASE/'runs/pilot'/photo/'result.json');cs=r['candidates']+r['filtered_candidates'];cache={};pr=[];start=time.perf_counter()
        for c in cs:
            p=c['classification'];b=p['canonical_object']['box']
            if not allrows and not (1170<=b[0]<=1200 and 920<=b[1]<=950):continue
            if allrows and c.get('recovery')=='r4_visible_part':continue # existing B classifier remains separate and unchanged
            z=dict(photo=photo,id=c['id'],box=b,baseline_keep=p['filter_recommendation']=='keep',baseline_pair=p['paired_evidence'],variants={})
            for pad in (2,4,8,12):
                for mode in ('center','letterbox'):
                    for side,ar in [('reference',ref),('target',tar)]:
                        im=adjusted_image(snap.manifest,crop(ar,b,pad,mode=='letterbox'));digest=hashlib.sha256(im.tobytes()).hexdigest()
                        if digest not in cache:cache[digest]=features(snap.manifest,snap.session,im)
                        if not allrows:im.save(OUT/'bank-review'/f'{photo}-{c["id"]}-{pad}-{mode}-{side}.png')
                        for label,bank in banks.items():
                            s=score(cache[digest],bank,47);z['variants'].setdefault(f'{mode}-{pad}-{label}',{})[side]=dict(s,input_sha256=digest)
                            if not allrows:
                                sim=(bank[:,:,0]@cache[digest][0]).max(axis=1);z['variants'][f'{mode}-{pad}-{label}'][side]['positive_neighbors']=(np.argsort(sim[:47])[-3:][::-1]+1).tolist()
            pr.append(z)
        save(dest,pr);np.savez_compressed(dest.with_suffix('.npz'),**cache);rows+=pr
        print('PHOTO',photo,'rows',len(pr),'seconds',round(time.perf_counter()-start,1),flush=True)
        if not allrows:
            for z in pr:print(z['id'],{k:round(v['target']['margin'],4) for k,v in z['variants'].items()},flush=True)
    save(OUT/('all-crop-bank-scores.json' if allrows else 'board-crop-bank-scores.json'),rows)
if __name__=='__main__':main()
