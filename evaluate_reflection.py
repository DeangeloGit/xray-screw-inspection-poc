import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import cv2,numpy as np
from detector import read,register,refine,structure_mask,machine_mask,correlation,proposals,write_image
from registration_candidate import choose_registration
import detector
register_one=getattr(detector,"_register_orientation",register)
ROOT=Path('workspace/windows-check/diagnostics/collected-data')


def evaluate(row):
 cv2.setNumThreads(2)
 out=ROOT/'reflection'/row['sha256'];out.mkdir(parents=True,exist_ok=True)
 try:
  ref=read(row['reference']);ref=cv2.resize(ref,None,fx=1536/max(ref.shape),fy=1536/max(ref.shape))
  raw=read(row['path']);reg=choose_registration(ref,raw,register_one,machine_mask,correlation)
  if not reg['mirrored']:
   result=dict(relative=row['relative'],sha256=row['sha256'],mirrored=False,count=row.get('count'),error=row.get('error'))
  else:
   target,flow,regions=refine(ref,reg['aligned'],structure_mask(ref)&reg['valid'])
   candidates,_=proposals(ref,target,machine_mask(ref)&reg['valid'],.13)
   np.savez_compressed(out/'aligned.npz',ref=ref,target=target,mask=machine_mask(ref)&reg['valid'])
   write_image(out/'aligned.png',(target*255).astype('uint8'));write_image(out/'reference.png',(ref*255).astype('uint8'))
   result=dict(relative=row['relative'],sha256=row['sha256'],mirrored=True,count=len(candidates),candidates=candidates,inliers=reg['inliers'],evidence=reg['orientation_evidence'],regions=regions,baseline_count=row.get('count'))
 except Exception as e:result=dict(relative=row['relative'],sha256=row['sha256'],error=str(e))
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
 return {k:v for k,v in result.items() if k not in ('candidates','regions')}


def main():
 rows=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'cache').glob('*/baseline.json')]
 rows=[r for r in rows if r['model']=='MPT11']
 with ProcessPoolExecutor(max_workers=2) as pool:
  for result in pool.map(evaluate,rows):print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
