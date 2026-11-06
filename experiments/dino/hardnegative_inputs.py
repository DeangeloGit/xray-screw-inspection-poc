"""Reconstruct exact classifier images and verify their inference input hashes."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-hardnegative-20261106/manual-normal'
os.environ['XRAY_WORKSPACE']=str(OUT/'input-review-runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from dino_paired_optimized import adjusted_image
from blackblock_ablation import cut
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
manifest=read(ROOT/'models/dino-paired-optimized-47-20261104-r3/manifest.json');scores={z['key']:z for z in read(OUT/'all-scores.json')};keys=read(OUT/'evaluation.json')['variants']['hardnegative_difference']['added']+['128-3'];proof=[];dest=OUT/'final/report/images';dest.mkdir(parents=True,exist_ok=True)
for k in keys:
    z=scores[k];arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{z["photo"]}.npz')
    for side,name in [('reference','ref'),('target','target')]:
        a=(np.clip(arr[name],0,1)*255).astype('uint8').astype('float32')/255
        im=adjusted_image(manifest,cut(a,z['box'],'original',z['reference_offset'] if side=='reference' else (0,0)))
        digest=hashlib.sha256(im.tobytes()).hexdigest();assert digest==z['pairs']['hardnegative'][side]['input_sha256']
        file=f'actual-{k}-{side}.png';im.save(dest/file);proof.append(dict(key=k,side=side,file=file,input_sha256=digest))
(OUT/'actual-input-proof.json').write_text(json.dumps(dict(all_input_hashes_match=True,rows=proof),indent=2),encoding='utf-8')
print('Actual input images verified',len(proof))
