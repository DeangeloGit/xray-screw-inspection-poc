"""One deterministic paired local crop recheck after contrast baseline rejection."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import read,save,sha,norm,MODEL
from experiments.dino.recenter_local_pilot import extract
from experiments.dino.contrast_pair_pilot import adjust
from dino_adapter import input_image
BASE=ROOT/'workspace/dino-learn-joint-20261103'
PREV=ROOT/'workspace/dino-contrast-pair-20261103'
OUT=ROOT/'workspace/dino-four-remaining-20261103'
def prepare():
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 data=read(BASE/'results.json');previous=read(PREV/'results.json')
 rules=dict(method='At most one geometric paired recheck of baseline-rejected candidates; existing baseline-positive pairs keep their actual baseline verdict.',
  crop='Existing local contour extractor: candidate-overlapping dark difference component; square long side plus2pixels on each side; same original-image coordinates on reference and target.',
  accepted='Existing context_reliable flag true (corr>=0.75, abs shifts<12), area>=12, contour not touching search-window boundaries, crop entirely inside image.',
  fallback='If baseline positive or geometry invalid use saved baseline. If valid recheck classify reference and target independently; keep only target_screw AND NOT reference_screw.',
  dino='Exact full47+65 contrast-adjusted equal-vote bank from previous experiment. Same1/99percentile contrast normalization, threshold0.',
  selection='Freeze geometry before inspecting new DINO scores; no manual positions, per-case thresholds, padding grid, best-score crop choice or added test examples.',
  scope='Same59 fixed cases. Offline only. This tests a cascade, not standalone model robustness.')
 save(OUT/'rules.json',rules)
 protected=read(PREV/'preservation-before.json');protected.update({str(p):sha(p) for p in [PREV/'results.json',PREV/'bank-features.npz',PREV/'features.npz',BASE/'results.json']})
 assert all(sha(Path(p))==h for p,h in protected.items());save(OUT/'preservation-before.json',protected)
 rows=[]
 for z,b in zip(data,previous):
  assert z['key']==b['key'];n=z['number'];ims=[Image.open(Path(z['source'])/f).convert('L') for f in ['reference.png','aligned.png']]
  if b['new']['keep']:ex=dict(valid=False,reason='baseline_pair_already_positive');accepted=False;box=None
  else:
   ex=extract(*[np.asarray(im,np.float32)/255 for im in ims],z['c']);accepted=bool(ex.get('valid'));box=None
   if accepted:
    x,y,s=ex['box'];box=[x-2,y-2,x+s+2,y+s+2];c=z['c'];e=32
    search=[max(e,c['x']-e),max(e,c['y']-e),min(ims[0].width-e,c['x']+c['w']+e),min(ims[0].height-e,c['y']+c['h']+e)]
    ox,oy,ow,oh=ex['object_box'];touch=ox<=search[0] or oy<=search[1] or ox+ow>=search[2] or oy+oh>=search[3]
    accepted=bool(ex['metrics']['context_reliable'] and ex['area']>=12 and not touch and min(box)>=0 and box[2]<=ims[0].width and box[3]<=ims[0].height)
    ex['touches_search_boundary']=touch
  row=dict(number=n,key=z['key'],group=z['group'],baseline=b['new'],extraction=ex,accepted=accepted,crop_box=box)
  rows.append(row)
  if n in [5,6,7,9]:
   c=z['c'];x,y,w,h=[c[k] for k in ['x','y','w','h']];old=[x-12,y-12,x+w+12,y+h+12];side=max(96,w+60,h+60);rx=round(x+w/2-side/2);ry=round(y+h/2-side/2)
   canvas=Image.new('RGB',(1240,900),'#f4f7f8');d=ImageDraw.Draw(canvas);font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',22)
   d.text((20,10),f'{z["name"]}／位置{z["id"]}：尚未看新DINO分數的取圖核對',font=font,fill='#173e4b')
   for col,(title,bx,color) in enumerate([('原圖，不畫框',None,None),('藍：上輪取圖',old,'#0076ca'),('橘：固定規則取圖',box,'#d86a00')]):
    d.text((20+col*410,52),title,font=font,fill=color or '#173e4b')
    for j,im in enumerate(ims):
     v=im.crop((rx,ry,rx+side,ry+side)).convert('RGB').resize((390,390));dr=ImageDraw.Draw(v)
     if bx:dr.rectangle([(bx[0]-rx)*390/side,(bx[1]-ry)*390/side,(bx[2]-rx)*390/side,(bx[3]-ry)*390/side],outline=color,width=2)
     canvas.paste(v,(20+col*410,90+j*400))
   canvas.save(OUT/'images'/f'{n}-geometry.png')
 save(OUT/'geometry.json',rows)
 print(json.dumps([dict(number=r['number'],accepted=r['accepted'],box=r['crop_box'],extraction=r['extraction']) for r in rows if r['number'] in [5,6,7,9]],ensure_ascii=False))

def run():
 import onnxruntime as ort
 data=read(BASE/'results.json');geometry=read(OUT/'geometry.json');m=read(MODEL/'manifest.json');bank=np.load(PREV/'bank-features.npz')['bank'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 cache=dict(np.load(PREV/'features.npz'));cp=OUT/'features.npz'
 if cp.exists():cache.update(dict(np.load(cp)))
 opt=ort.SessionOptions();opt.intra_op_num_threads=4;session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opt,providers=['CPUExecutionProvider'])
 def classify(im):
  key=hashlib.sha256(im.tobytes()).hexdigest()
  if key not in cache:
   a=np.asarray(im,np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
   raw=session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];cache[key]=np.stack([norm(raw[0]),norm(raw[1:].mean(axis=0))])
  v=cache[key];scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
  parts=[float(np.sort(s[labels])[-3:].mean()-np.sort(s[~labels])[-3:].mean()) for s in scores];margin=sum(parts)/2
  return dict(screw=margin>=0,margin=margin,whole_margin=parts[0],local_margin=parts[1],input_sha256=key)
 rows=[]
 for z,g in zip(data,geometry):
  n=z['number'];assert g['key']==z['key']
  if g['accepted']:
   pair={}
   for side,f in [('reference','reference.png'),('target','aligned.png')]:
    full=Image.open(Path(z['source'])/f).convert('L');inp=adjust(input_image(m,np.asarray(full.crop(g['crop_box']),np.float32)/255));inp.save(OUT/'images'/f'{n}-{side}.png');pair[side]=classify(inp)
   pair['keep']=pair['target']['screw'] and not pair['reference']['screw'];method='one_geometry_recheck'
  else:
   pair=g['baseline'];method='saved_baseline'
   for side in ['reference','target']:Image.open(PREV/'images'/f'{n}-{side}.png').save(OUT/'images'/f'{n}-{side}.png')
  row=dict(**g,new=pair,method=method,correct=not pair['keep'] if z['group']=='normal' else pair['keep']);rows.append(row)
 np.savez(cp,**cache);save(OUT/'results.json',rows)
 summary={}
 for group in ['original_screw','extra_confirmed','five_visual_screws','normal']:
  rs=[r for r in rows if r['group']==group];summary[group]=dict(total=len(rs),kept=sum(r['new']['keep'] for r in rs),wrong=[r['number'] for r in rs if not r['correct']])
 summary['rechecks']=sum(r['accepted'] for r in rows);summary['remaining_four']=[dict(number=n,correct=rows[n-1]['correct'],method=rows[n-1]['method']) for n in [5,6,7,9]]
 save(OUT/'summary.json',summary);protected=read(OUT/'preservation-before.json');assert all(sha(Path(p))==v for p,v in protected.items());save(OUT/'preservation.json',dict(unchanged=True,files=len(protected),production_changes=False))
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='run':run()
 else:prepare()
