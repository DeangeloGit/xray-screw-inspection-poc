"""4r diagnostic: one human-confirmed normal connector, no candidate-ID rule."""
import os, sys, json, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-connector-20261106'
AUDIT=ROOT/'workspace/dino-4r-example-audit-20261106'
PRIOR=ROOT/'workspace/dino-4r-crossbatch-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image, example_features
from example_audit_policy import square_crop
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    import cv2
    cv2.setNumThreads(4);OUT.mkdir(parents=True,exist_ok=True)
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays/128.npz');tar=(np.clip(a['target'],0,1)*255).astype('uint8').astype('float32')/255
    # Use #22 only as normal example. #40 is a separate diagnostic target,
    # but both were inspected during development and are NOT blind holdouts.
    normal=square_crop(tar,[1400,941,22,58],4)
    proto=example_features(snap.manifest,snap.session,normal)[None]
    np.savez_compressed(OUT/'normal-connector-bank.npz',bank=proto,aspect=np.float32(58/22))
    adjusted_image(snap.manifest,normal).save(OUT/'normal-example-22.png')
    save(OUT/'human-confirmations.json',dict(source='User explicitly confirmed both normal / exclude in current chat',cases=[dict(photo='ng-128',candidate=i,label='normal',role='training' if i==22 else 'development_check') for i in (22,40)],original_records_modified=False))
    bank=np.load(AUDIT/'letterbox-112-bank.npz')['bank'];scores=read(AUDIT/'all-crop-bank-scores.json');current={c['key']:c for c in read(PRIOR/'cases.json')};rows=[]
    for photo in map(str,range(128,138)):
        cache=np.load(AUDIT/'all-features'/f'{photo}.npz')
        for z in scores:
            if z['photo']!=photo:continue
            c=current[f'ng-{photo}-{z["id"]}'];checks=[]
            for pad in (2,4,8,12):
                s=z['variants'][f'letterbox-{pad}-allbank']['target'];v=cache[s['input_sha256']]
                normal_sim=[float((proto[:,:,i]@v[i]).max()) for i in (0,1)]
                screw_sim=[float((bank[:47,:,i]@v[i]).max()) for i in (0,1)]
                checks.append(dict(pad=pad,normal=normal_sim,strongest_screw=screw_sim,margin=s['margin'],normal_wins=all(n>p for n,p in zip(normal_sim,screw_sim))))
            veto=all(q['normal_wins'] and q['margin']<0 for q in checks)
            row=dict(photo=photo,id=z['id'],box=z['box'],keep=c['keep'],answers=c['answers'],veto=veto,checks=checks);rows.append(row)
            if (c['keep'] and veto) or (photo=='128' and z['id'] in (22,40,19)):
                print(photo,z['id'],'keep',c['keep'],'answers',c['answers'],'veto',veto,'minimum gaps',[round(min(n-p for n,p in zip(q['normal'],q['strongest_screw'])),3) for q in checks],flush=True)
    save(OUT/'cached-normal-probe.json',rows)
    canvas=Image.new('RGB',(896,535),'white');d=ImageDraw.Draw(canvas)
    for row,(cid,b) in enumerate(((40,[1400,842,22,73]),(22,[1400,941,22,58]))):
        for col,(title,pad,square) in enumerate((('old center pad12',12,False),('full shape pad2',2,True),('full shape pad4',4,True),('full shape pad12',12,True))):
            x,y,w,h=b;crop=square_crop(tar,b,pad) if square else tar[y-pad:y+h+pad,x-pad:x+w+pad]
            im=adjusted_image(snap.manifest,crop);im.save(OUT/f'input-{cid}-{col}.png');canvas.paste(im,(col*224,row*265+30));d.text((col*224+4,row*265+6),f'#{cid} {title}',fill='black')
    canvas.save(OUT/'actual-inputs.png')
if __name__=='__main__':main()
