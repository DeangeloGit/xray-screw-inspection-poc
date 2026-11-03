import cv2,json,hashlib,shutil
import numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/windows-check/diagnostics/clip-screw-examples';OUT.mkdir(exist_ok=True)
names=['53bd66f8-121f-4500-915e-4dd81adddd27','0a552208-2813-4858-9a29-73fa219b9d50','7d5b8fe4-7ae2-4b04-aa6f-3f98ae7a240f']
items=[]
for page,name in enumerate(names,1):
 p=Path('C:/Users/DEANGE~1/AppData/Local/Temp')/('codex-clipboard-'+name+'.png');shutil.copy2(p,OUT/f'source-{page}.png')
 if page==3:continue
 im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR);b,g,r=cv2.split(im)
 mask=((r.astype(float)>g.astype(float)*1.45)&(r.astype(float)>b.astype(float)*1.45)&(r>120)).astype('uint8')*255
 mask[:int(im.shape[0]*(.48 if page==1 else .20))]=0
 contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 rects=[]
 for c in contours:
  (cx,cy),(w,h),angle=cv2.minAreaRect(c)
  if min(w,h)<15 or max(w,h)>115 or max(w,h)/min(w,h)>4 or cv2.contourArea(c)<.65*w*h:continue
  rects.append((cy,cx,w,h,angle,c))
 for j,(cy,cx,w,h,angle,c) in enumerate(sorted(rects),1):
  box=cv2.boxPoints(((cx,cy),(w,h),angle)).astype('float32')
  # Perspective-warp the annotated rectangle, then exclude its colored boundary.
  target=np.array([[0,h-1],[0,0],[w-1,0],[w-1,h-1]],np.float32)
  patch=cv2.warpPerspective(im,cv2.getPerspectiveTransform(box,target),(round(w),round(h)))
  patch=patch[4:-4,4:-4]
  if min(patch.shape[:2])<9:continue
  gray=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY);file=f'screw-p{page}-{j}.png'
  cv2.imencode('.png',gray)[1].tofile(OUT/file)
  items.append(dict(id=file,page=page,split='bank' if page==1 else 'validation',box=[cx,cy,w,h,angle],file=file))
contact=Image.new('RGB',(1000,((len(items)+9)//10)*125),'white');d=ImageDraw.Draw(contact)
for i,z in enumerate(items):
 im=Image.open(OUT/z['file']);im.thumbnail((90,95));x=(i%10)*100;y=(i//10)*125;contact.paste(im,(x,y+22));d.text((x,y),z['file'].replace('screw-',''),fill='black')
contact.save(OUT/'extracted.png');(OUT/'examples.json').write_text(json.dumps(items,indent=2));print('extracted',len(items),'bank',sum(z['page']==1 for z in items),'validation',sum(z['page']==2 for z in items))
