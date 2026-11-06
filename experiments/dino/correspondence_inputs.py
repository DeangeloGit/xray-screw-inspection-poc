"""Reproduce and hash-check the actual four-case DINO image inputs."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-correspondence-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'input-review-runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from dino_adapter import input_image
from dino_paired_optimized import adjusted_image
from correspondence_policy import crop
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
manifest=read(ROOT/'models/dino-paired-optimized-47-20261104-r3/manifest.json')
arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays/128.npz');ref,tar=[(np.clip(arr[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
r=read(OUT/'final/runs/pilot/128/result.json');dest=OUT/'final/report/images';dest.mkdir(exist_ok=True,parents=True);proof=[]
for n in (10,80,82,103):
    c=next(c for c in r['candidates']+r['filtered_candidates'] if c['id']==n);p=c['classification'];meta=p['correspondence_experiment'];canonical=dict(zip(('x','y','w','h'),p['canonical_object']['box']))
    pads=(4,8,12) if n in (10,82,103) else (12,)
    for pad in pads:
        dx,dy=meta['reference_offset'];crops=[crop(ref,canonical,pad,dx,dy),crop(tar,canonical,pad)]
        if meta['recheck']=='shared_contrast_reference':
            a=[np.asarray(input_image(manifest,z).convert('L'),np.float32) for z in crops];low,high=np.percentile(a[1],[1,99]);images=[Image.fromarray(np.rint(np.clip((z-low)/max(1,high-low),0,1)*255).astype('uint8')).convert('RGB') for z in a];pred=meta['shared_views'][str(pad)]
        else:
            images=[adjusted_image(manifest,z) for z in crops];pred=meta['contour_views'][str(pad)] if 'contour_views' in meta else p
        row=dict(candidate=n,pad=pad,files=[])
        for side,im in zip(('reference','target'),images):
            digest=hashlib.sha256(im.tobytes()).hexdigest();assert digest==pred['paired_evidence'][side]['input_sha256'],(n,pad,side)
            name=f'input-128-{n}-pad{pad}-{side}.png';im.save(dest/name);row['files'].append(name)
        proof.append(row)
(OUT/'actual-input-proof.json').write_text(json.dumps(dict(all_input_hashes_match=True,rows=proof),indent=2),encoding='utf-8')
print('Matched actual input hashes:',len(proof)*2)
