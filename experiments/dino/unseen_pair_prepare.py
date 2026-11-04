"""Prepare provenance/visual review BEFORE evaluating the fixed equal-vote method."""
import sys,json,hashlib,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import read,save,MODEL,PRIOR
BASE=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103'
FULL=ROOT/'workspace/windows-check/diagnostics/dino-47-paired-full-20261103'
OUT=ROOT/'workspace/dino-unseen-equal-pair-20261103'
def font(n):return ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',n)
def main():
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 cases=read(FULL/'cases.json');idx={z['key']:z for z in cases};cats={z['key']:z['category'] for z in read(FULL/'review-index.json')}
 m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json');old=read(PRIOR/'plan.json')['cases']
 bankphotos={s.rsplit('-',1)[0] for s in m['example_bank']['normal']['ids']};oldphotos={z.get('sha') for z in old}
 audit=read(ROOT/'workspace/dino-two-directions-20261103/visual-audit.json')
 keys=list(dict.fromkeys([z['key'] for z in cases if z['known']]+[z['key'] for z in audit['b']]+[z['key'] for z in audit['a'] if z['status']=='疑似新增螺絲會被誤刪']))
 positives=[]
 for k in keys:
  z=idx[k]
  if z['sha'] in bankphotos or z['sha'] in oldphotos:continue
  positives.append(dict(number=len(positives)+1,**z,category='unknown',source=str(BASE/'photos'/z['sha'])))
 normals=[dict(**z,category=cats[z['key']],source=str(BASE/'photos'/z['sha'])) for z in cases if z['label']=='OK' and z['sha'] not in bankphotos and z['sha'] not in oldphotos]
 save(OUT/'screening-pool.json',dict(positive_review=positives,normal_eligible=normals,bank_normal_source_photos=sorted(bankphotos),previous_test_source_photos=sorted(p for p in oldphotos if p),
  selection='All pre-existing known/suspected screw positions for visual provenance audit; all OK candidates outside known bank source photos and prior17 source photos. No new-method scores used.',
  field_bank_provenance='16 user montage crops have no original filename/coordinate provenance; require visual duplicate review and do not claim fully independent unseen-source verification.'))
 def contacts(items,prefix):
  for start in range(0,len(items),8):
   batch=items[start:start+8];canvas=Image.new('RGB',(1100,310*math.ceil(len(batch)/2)),'#f4f7f8');d=ImageDraw.Draw(canvas)
   for j,z in enumerate(batch):
    xx=(j%2)*550;yy=(j//2)*310;c=z['c'];x,y,w,h=[c[k] for k in ['x','y','w','h']];side=max(90,w+48,h+48)
    d.text((xx+5,yy+3),f'{start+j+1}. {z["machine"]} #{z["id"]} '+Path(z['name']).stem[-12:],font=font(17),fill='#173e4b')
    for col,f in enumerate(['reference.png','aligned.png']):
     im=Image.open(Path(z['source'])/f).convert('RGB');x0=max(0,min(im.width-side,round(x+w/2-side/2)));y0=max(0,min(im.height-side,round(y+h/2-side/2)));crop=im.crop((x0,y0,x0+side,y0+side)).resize((265,265));draw=ImageDraw.Draw(crop);k=265/side
     draw.rectangle([(x-x0)*k,(y-y0)*k,(x+w-x0)*k,(y+h-y0)*k],outline='#e02e44',width=2);canvas.paste(crop,(xx+col*275,yy+35))
   canvas.save(OUT/f'{prefix}-{start//8+1}.jpg',quality=94)
 contacts(positives,'screw-review');contacts(normals,'normal-review')
 for label in ['screw','normal']:
  ids=m['example_bank'][label]['ids']
  for start in range(0,len(ids),24):
   batch=ids[start:start+24];canvas=Image.new('RGB',(1200,215*math.ceil(len(batch)/6)),'white');d=ImageDraw.Draw(canvas)
   for j,k in enumerate(batch):
    x=(j%6)*200;y=(j//6)*215;d.text((x+4,y+2),f'{start+j+1}. '+('現場' if k.startswith('upload-') else k[:16]),font=font(17),fill='black')
    im=Image.open(MODEL/'examples'/meta[k]['file']).convert('RGB');scale=min(180/im.width,180/im.height);im=im.resize((round(im.width*scale),round(im.height*scale)));canvas.paste(im,(x+5,y+28))
   canvas.save(OUT/f'bank-{label}-{start//24+1}.jpg',quality=94)
 print(json.dumps(dict(screw_review=len(positives),normal_eligible=len(normals)),ensure_ascii=False))
if __name__=='__main__':main()
