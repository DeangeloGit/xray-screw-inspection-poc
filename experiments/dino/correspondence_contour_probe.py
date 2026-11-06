"""Diagnostic crop/context scores, without changing any inference results."""
import os,sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-correspondence-20261106'
os.environ['XRAY_WORKSPACE']=str(OUT/'probe-runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
import cv2
cv2.setNumThreads(4)
snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays/128.npz');ref,tar=[(np.clip(arr[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
r=json.loads((ROOT/'workspace/dino-4r-stability-20261106/final/runs/pilot/128/result.json').read_text(encoding='utf-8'));rows=[]
from correspondence_geometry import contours
for c in r['candidates']+r['filtered_candidates']:
    if c['id'] not in (10,80,82,103):continue
    boxes={tuple(g['box']) for g in contours(tar,c)}
    for x,y,w,h in sorted(boxes):
        for pad in (4,8,12):
            sl=np.s_[y-pad:y+h+pad,x-pad:x+w+pad];pred=snap.classify(tar[sl],reference_crop=ref[sl]);ev=pred['paired_evidence']
            row=dict(id=c['id'],box=[x,y,w,h],pad=pad,prediction=pred);rows.append(row)
            print(c['id'],[x,y,w,h],pad,pred['filter_recommendation'],{s:round(ev[s]['screw_margin'],4) for s in ('reference','target')},flush=True)
(OUT/'contour-crop-probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
