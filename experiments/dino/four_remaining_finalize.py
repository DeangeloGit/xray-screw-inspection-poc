"""Evaluate a restricted follow-up from saved predictions, and expose neighbors."""
import sys, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.four_remaining_pilot import OUT, PREV, BASE, MODEL, read, save, sha

def main():
 raw=read(OUT/'results.json'); old=read(PREV/'results.json'); base=read(BASE/'results.json')
 rules=read(OUT/'rules.json')
 rules['restricted_followup']='Only recheck if BOTH baseline reference and target already classify screw, and geometry accepted. Otherwise use saved baseline pair. Never turn a baseline-negative target into a screw by recropping.'
 rules['development_disclosure']='Restriction added after the unrestricted experiment created wire false positives44,50. Same59 development cases; not independent validation.'
 save(OUT/'restricted-rules.json',rules)
 rows=[]
 for r,b in zip(raw,old):
  p=b['new'];use=bool(p['reference']['screw'] and p['target']['screw'] and r['accepted'])
  pair=r['new'] if use else p
  correct=(not pair['keep']) if r['group']=='normal' else pair['keep']
  z=dict(number=r['number'],key=r['key'],group=r['group'],baseline=p,new=pair,rechecked=use,correct=correct)
  hashes={}
  for side in ['reference','target']:
   src=(OUT if use else PREV)/'images'/f'{r["number"]}-{side}.png'
   im=Image.open(src).convert('RGB');h=hashlib.sha256(im.tobytes()).hexdigest()
   expected=r['new'][side]['input_sha256'] if use else b['input_hashes'][side]
   assert h==expected
   im.save(OUT/'images'/f'{r["number"]}-final-{side}.png');hashes[side]=h
  z['input_hashes']=hashes;rows.append(z)
 save(OUT/'restricted-results.json',rows)
 summary={}
 for group in ['original_screw','extra_confirmed','five_visual_screws','normal']:
  rs=[r for r in rows if r['group']==group]
  summary[group]=dict(total=len(rs),correct=sum(r['correct'] for r in rs),wrong=[r['number'] for r in rs if not r['correct']])
 summary['rechecked']=[r['number'] for r in rows if r['rechecked']]
 summary['remaining_four']={str(n):rows[n-1]['correct'] for n in [5,6,7,9]}
 assert all(rows[n-1]['correct'] for n in [1,2,3,4,8])
 assert all(r['correct'] for r in rows if r['group']=='normal')
 save(OUT/'restricted-summary.json',summary)
 # Exact neighbors explaining baseline scores, not an attribution heat map.
 m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json')
 ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids']
 bank=np.load(PREV/'bank-features.npz')['bank'];cache=np.load(PREV/'features.npz')
 labels=np.r_[np.ones(47,bool),np.zeros(65,bool)];diagnostics=[]
 font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',20)
 for n,side in [(5,'target'),(6,'reference'),(7,'target'),(9,'reference')]:
  v=cache[old[n-1]['input_hashes'][side]]
  scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
  canvas=Image.new('RGB',(1260,500),'#f4f7f8');d=ImageDraw.Draw(canvas)
  d.text((12,8),f'{base[n-1]["name"]}／{base[n-1]["id"]}：上一輪'+('待測圖' if side=='target' else '參照圖')+'比到的範例',font=font,fill='#173e4b')
  detail=dict(number=n,side=side,branches=[])
  for j,(branch,sc) in enumerate(zip(['整體外觀','小區域平均'],scores)):
   y=45+j*225
   d.text((12,y),branch+'：輸入圖',font=font,fill='#173e4b')
   canvas.paste(Image.open(PREV/'images'/f'{n}-{side}.png').resize((150,150)),(12,y+33))
   branchdata=dict(branch=branch)
   for cl,clname in [(True,'螺絲'),(False,'正常')]:
    indices=np.where(labels==cl)[0];top=indices[np.argsort(sc[indices])[-3:][::-1]]
    branchdata[clname]=[dict(id=ids[i],score=float(sc[i])) for i in top]
    for k,i in enumerate(top):
     x=185+(k+(0 if cl else 3))*175
     d.text((x,y),f'{clname}{k+1}：{sc[i]:.3f}',font=font,fill='#173e4b')
     # Show actual normalized bank view selected for this comparison.
     from experiments.dino.contrast_pair_pilot import adjust
     from dino_adapter import input_image
     im=Image.open(MODEL/'examples'/meta[ids[i]]['file']).convert('L')
     im=adjust(input_image(m,np.asarray(im,np.float32)/255))
     view=int(np.argmax(bank[i,:,0]@v[0])) if j==0 else 0
     if view>=4:im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
     im=im.rotate((view%4)*90)
     canvas.paste(im.resize((150,150)),(x,y+33))
     d.text((x,y+186),ids[i][:22],font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',13),fill='#173e4b')
   detail['branches'].append(branchdata)
  canvas.save(OUT/'images'/f'{n}-neighbors.png');diagnostics.append(detail)
 save(OUT/'neighbors.json',diagnostics)
 protected=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in protected.items())
 save(OUT/'preservation.json',dict(unchanged=True,files=len(protected),production_changes=False))
 print(summary)
if __name__=='__main__':main()
