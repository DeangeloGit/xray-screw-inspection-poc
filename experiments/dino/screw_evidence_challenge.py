"""Synthetic challenge only: can a plain dark rectangle trigger the retired rescue?"""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np,cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-screw-evidence-20261106';PREV=ROOT/'workspace/dino-4r-hardnegative-20261106/manual-normal'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_paired_optimized import features,adjusted_image
from hardnegative_policy import cut,score,difference,gate
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def main():
    cv2.setNumThreads(4);plan=read(PREV/'final/plan.json');snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error
    bank=np.load(PREV/'experimental-bank.npz')['bank'];conf=read(PREV/'training-selection.json')['selected']['hardnegative']['config'];records=[];dest=OUT/'challenges';dest.mkdir(exist_ok=True)
    inputs=read(PREV/'all-scores.json')
    for photo in ('128','131','132'):
        z=next(z for z in inputs if z['photo']==photo and z['key'] in read(PREV/'evaluation.json')['variants']['hardnegative_difference']['added']);b=z['box'];x,y,w,h=b
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');ref=(np.clip(a['ref'],0,1)*255).astype('uint8').astype('float32')/255
        for value in (.02,.05,.08):
            # Start from the reference. Add only a filled rectangle: no screw,
            # no target patch, no target screw pixels or generated texture.
            mask=np.zeros_like(ref,np.float32);mask[y:y+h,x:x+w]=1;mask=cv2.GaussianBlur(mask,(0,0),.7)
            target=ref*(1-mask)+value*mask;target=(np.clip(target,0,1)*255).astype('uint8').astype('float32')/255;pair={};name=f'{photo}-flat-{value:.2f}'
            for side,im in [('reference',ref),('target',target)]:
                crop=cut(im,b,'original');view=adjusted_image(snap.manifest,crop);view.save(dest/f'{name}-{side}.png');v=features(snap.manifest,snap.session,view);pair[side]=score(v,bank,50)
            diff=difference(ref,target,b);result=dict(name=name,photo=photo,value=value,box=b,pair=pair,difference=diff,rescue_gate=gate(pair,diff,conf),expected='exclude: synthetic rectangle only',not_real_data=True);records.append(result)
            print(name,'target',round(pair['target']['margin'],4),'ref',round(pair['reference']['margin'],4),'gate',result['rescue_gate'],flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in plan['hashes'].items())
    (OUT/'synthetic-challenge.json').write_text(json.dumps(dict(purpose='diagnostic, not real-image validation; no answer changes',rows=records,false_rescues=sum(r['rescue_gate'] for r in records)),ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
