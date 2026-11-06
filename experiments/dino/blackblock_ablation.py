"""Fixed 2x2 crop/bank experiment. New examples only from declared training photos."""
import os,sys,json,hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-blackblock-20261106';BASE=ROOT/'workspace/dino-4r-correspondence-20261106/final'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image,features,example_features
import cv2
cv2.setNumThreads(4)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def cut(im,b,mode,offset=(0,0)):
    x,y,w,h=b;x+=offset[0];y+=offset[1]
    if mode=='original':x0,y0,X,Y=x-12,y-12,x+w+12,y+h+12
    else:
        side=max(w,h)+8;x0=round(x+w/2-side/2);y0=round(y+h/2-side/2);X,Y=x0+side,y0+side
    return im[max(0,y0):Y,max(0,x0):X]
def score(v,bank,n):
    similarities=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
    margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in similarities]
    return dict(margin=sum(margins)/2,whole=margins[0],local=margins[1])
def main():
    plan=read(OUT/'experiment-plan.json');snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error
    assert snap.identity==plan['model']['fingerprint']
    freeze={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),OUT/'experiment-plan.json',OUT/'answers-corrected.json')};save(OUT/'ablation-frozen.json',freeze)
    (OUT/'features').mkdir(exist_ok=True);(OUT/'training-examples').mkdir(exist_ok=True)
    n=len(snap.manifest['example_bank']['screw']['ids']);added=[]
    for e in plan['added_examples']:
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{e["photo"]}.npz');tar=(np.clip(a['target'],0,1)*255).astype('uint8').astype('float32')/255
        crop=cut(tar,e['box'],'original');Image.fromarray(np.uint8(crop*255)).save(OUT/'training-examples'/f'{e["photo"]}.png');added.append(example_features(snap.manifest,snap.session,crop))
    newbank=np.concatenate((snap.feature_bank[:n],np.asarray(added),snap.feature_bank[n:]));np.savez_compressed(OUT/'experimental-bank.npz',bank=newbank)
    rows=[]
    for key in [str(i) for i in range(128,138)]+['golden']:
        dest=OUT/'features'/f'{key}.json'
        if dest.exists():rows+=read(dest);continue
        t=time.perf_counter();a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{key}.npz');ref,tar=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')];r=read(BASE/'runs/pilot'/key/'result.json');photo=[];cache={}
        for c in r['candidates']+r['filtered_candidates']:
            p=c['classification'];b=p['canonical_object']['box'];offset=p['correspondence_experiment']['reference_offset'];rec=dict(photo=key,id=c['id'],baseline_keep=p['filter_recommendation']=='keep',box=b,reference_offset=offset,variants={})
            for mode in ('original','square'):
                for side,im in [('reference',ref),('target',tar)]:
                    image=adjusted_image(snap.manifest,cut(im,b,mode,offset if side=='reference' else (0,0)));digest=hashlib.sha256(image.tobytes()).hexdigest()
                    if digest not in cache:cache[digest]=features(snap.manifest,snap.session,image)
                    for label,bank,pos in [('old',snap.feature_bank,n),('new',newbank,n+3)]:
                        rec['variants'].setdefault(mode+'_'+label,{})[side]=dict(score(cache[digest],bank,pos),input_sha256=digest)
            for v in rec['variants'].values():v['keep']=v['target']['margin']>=0 and v['reference']['margin']<0
            photo.append(rec)
        save(dest,photo);np.savez_compressed(OUT/'features'/f'{key}.npz',**cache);rows+=photo;print('ABLATION',key,len(photo),'seconds',round(time.perf_counter()-t,1),flush=True)
    save(OUT/'ablation-results.json',rows)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in plan['protected_hashes'].items())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in freeze.items())
    save(OUT/'ablation-complete.json',dict(candidates=len(rows),fresh_features=True,protected_hashes_unchanged=True,bank_original_retained=True,new_training_examples=3,training_photos=plan['training_photos'],heldout_photos=plan['heldout_photos']))
if __name__=='__main__':main()
