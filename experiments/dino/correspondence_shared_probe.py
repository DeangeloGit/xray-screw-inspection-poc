"""Check shared contrast normalization of low-contrast reference images."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-correspondence-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'shared-probe-runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
from dino_adapter import input_image
from dino_paired_optimized import features
from correspondence_policy import crop
import cv2
cv2.setNumThreads(4)
snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
rows=[]
for key in map(str,range(128,138)):
    arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{key}.npz');ref,tar=[(np.clip(arr[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
    r=json.loads((ROOT/'workspace/dino-4r-stability-20261106/final/runs/pilot'/key/'result.json').read_text(encoding='utf-8'))
    for c in r['candidates']+r['filtered_candidates']:
        pred=c['classification'];pair=pred['paired_evidence']
        if not (pair['target']['label']=='screw' and crop(ref,c,0).std()<.025 and crop(tar,c,0).std()>.12):continue
        for pad in (4,8,12):
            images=[np.asarray(input_image(snap.manifest,crop(im,c,pad)).convert('L'),np.float32) for im in (ref,tar)]
            low,high=np.percentile(images[1],[1,99]);scores={}
            for side,a in zip(('reference','target'),images):
                im=Image.fromarray(np.rint(np.clip((a-low)/max(1,high-low),0,1)*255).astype('uint8')).convert('RGB')
                v=features(snap.manifest,snap.session,im);bank=snap.feature_bank;n=len(snap.manifest['example_bank']['screw']['ids'])
                vals=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]];margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in vals]
                scores[side]=dict(margin=sum(margins)/2,parts=margins,sha256=hashlib.sha256(im.tobytes()).hexdigest())
            row=dict(photo=key,id=c['id'],pad=pad,low=float(low),high=float(high),scores=scores);rows.append(row)
            print(key,c['id'],pad,{s:round(z['margin'],4) for s,z in scores.items()},flush=True)
(OUT/'shared-contrast-probe.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
