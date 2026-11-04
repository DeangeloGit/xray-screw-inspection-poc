"""One predeclared visible continuity gate; no per-case thresholds or crops."""
import sys,json,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import read,save,sha
PRIOR=ROOT/'workspace/dino-learn-joint-20261103'
OUT=ROOT/'workspace/dino-through-line-20261103'
def inspect(im):
 a=np.asarray(im.convert('L'));threshold,mask=cv2.threshold(a,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
 count,labels,stats,_=cv2.connectedComponentsWithStats(mask)
 # Fixed central half overlaps the original candidate. No scoring by DINO.
 ids,hits=np.unique(labels[56:168,56:168],return_counts=True);pool=[(int(n),int(k)) for k,n in zip(ids,hits) if k>0]
 if not pool:return dict(through=False,threshold=float(threshold),reason='no central dark component'),np.zeros_like(mask)
 _,label=max(pool);comp=labels==label
 edges={name:bool(a.any()) for name,a in [('left',comp[:,0]),('right',comp[:,-1]),('top',comp[0]),('bottom',comp[-1])]}
 through=(edges['left'] and edges['right']) or (edges['top'] and edges['bottom'])
 return dict(through=bool(through),threshold=float(threshold),edges=edges,box=stats[label,:4].tolist(),area=int(comp.sum())),comp.astype('uint8')*255
def main():
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 rule=dict(base='Previous full47+65 equal-vote classifier; original unchanged224 crops',
  mask='Otsu dark threshold,8-connected component with maximum overlap in central112x112; ties by component index',
  gate='If selected component touches both left/right or both top/bottom image boundaries, classify non-screw by geometry gate; otherwise use unchanged equal-vote decision.',
  applies='Identical gate on both reference and target, on all59 cases',
  no_parameter_search=True,scope='This is a geometric rule added to DINO, NOT an improvement inside DINO; may reject real screws connected to background.')
 save(OUT/'rules.json',rule);rows=[]
 for z in read(PRIOR/'results.json'):
  pair={};evidence={};n=z['number']
  for side in ['reference','target']:
   im=Image.open(z['image_base']+'-'+side+'.png');ev,mask=inspect(im);evidence[side]=ev
   pair[side]=dict(screw=z['equal'][side]['screw'] and not ev['through'],basis='through_line_gate' if ev['through'] else 'equal_dino')
   Image.fromarray(mask).save(OUT/'images'/f'{n}-{side}-mask.png')
  pair['keep']=pair['target']['screw'] and not pair['reference']['screw'];rows.append(dict(number=n,key=z['key'],group=z['group'],new=pair,evidence=evidence,correct=not pair['keep'] if z['group']=='normal' else pair['keep']))
 summary={}
 for group in ['original_screw','extra_confirmed','five_visual_screws','normal']:
  rs=[r for r in rows if r['group']==group];summary[group]=dict(total=len(rs),kept=sum(r['new']['keep'] for r in rs),wrong=[r['number'] for r in rs if not r['correct']])
 summary['focus_wire']=dict(number=10,false_alarm=rows[9]['new']['keep'])
 save(OUT/'results.json',rows);save(OUT/'summary.json',summary)
 protected=read(PRIOR/'preservation-before.json');assert all(sha(Path(p))==h for p,h in protected.items())
 save(OUT/'preservation.json',dict(protected_files=len(protected),unchanged=True,production_changes=False))
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
