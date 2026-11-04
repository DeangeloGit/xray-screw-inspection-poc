"""Fixed luminance normalization, full bank, same59 cases. Offline only."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import read,save,sha,norm,MODEL
from dino_adapter import input_image
PRIOR=ROOT/'workspace/dino-learn-joint-20261103'
OLD=ROOT/'workspace/dino-fixed-crop-recognition-20261103'
OUT=ROOT/'workspace/dino-contrast-pair-20261103'
def adjust(im):
 a=np.asarray(im.convert('L'),np.float32);low,high=np.percentile(a,[1,99])
 if high-low<1:return im.convert('RGB')
 return Image.fromarray(np.rint(np.clip((a-low)/(high-low),0,1)*255).astype('uint8')).convert('RGB')
def main():
 import onnxruntime as ort
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 rules=dict(percentiles=[1,99],operation='Linear contrast stretch per image after original224 preprocessor; clamp tails. Same transformation for all bank/query images.',
  base_method='Exact full47+65 bank, max8view CLS top3 margin and original-view patch mean top3 margin averaged equally; zero threshold.',
  selection='Fixed rule before reading adjusted test scores, follow-up motivated by dark missed screws; no parameter search.',
  scope='Same59 cases, no crop/geometry changes, no new training examples; no production changes.')
 save(OUT/'rules.json',rules)
 m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json');ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 protected=read(PRIOR/'preservation-before.json');protected[str(PRIOR/'results.json')]=sha(PRIOR/'results.json');save(OUT/'preservation-before.json',protected)
 cp=OUT/'features.npz';cache=dict(np.load(cp)) if cp.exists() else {}
 opts=ort.SessionOptions();opts.intra_op_num_threads=4
 session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
 def feature(im):
  key=hashlib.sha256(im.tobytes()).hexdigest()
  if key not in cache:
   a=np.asarray(im,np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
   raw=session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];cache[key]=np.stack([norm(raw[0]),norm(raw[1:].mean(axis=0))])
  return cache[key]
 bank=[]
 for i,k in enumerate(ids):
  im=Image.open(MODEL/'examples'/meta[k]['file']).convert('L');im=adjust(input_image(m,np.asarray(im,np.float32)/255));views=[]
  for flip in [False,True]:
   a=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else im
   for angle in [0,90,180,270]:views.append(feature(a.rotate(angle)))
  bank.append(np.stack(views))
  if i%14==0:np.savez(cp,**cache);print('adjusted examples',i+1,'/112',flush=True)
 bank=np.stack(bank);np.savez(OUT/'bank-features.npz',bank=bank)
 def compare(v):
  whole=(bank[:,:,0]@v[0]).max(axis=1);local=bank[:,0,1]@v[1];parts=[]
  for scores in [whole,local]:parts.append(float(np.sort(scores[labels])[-3:].mean()-np.sort(scores[~labels])[-3:].mean()))
  val=sum(parts)/2;return dict(screw=val>=0,margin=val,whole_margin=parts[0],local_margin=parts[1])
 rows=[]
 for z in read(PRIOR/'results.json'):
  pair={};hashes={};n=z['number']
  for side in ['reference','target']:
   im=adjust(Image.open(z['image_base']+'-'+side+'.png'));pair[side]=compare(feature(im));hashes[side]=hashlib.sha256(im.tobytes()).hexdigest();im.save(OUT/'images'/f'{n}-{side}.png')
  pair['keep']=pair['target']['screw'] and not pair['reference']['screw'];rows.append(dict(number=n,key=z['key'],group=z['group'],new=pair,input_hashes=hashes,correct=not pair['keep'] if z['group']=='normal' else pair['keep']))
 np.savez(cp,**cache);save(OUT/'results.json',rows)
 summary={}
 for group in ['original_screw','extra_confirmed','five_visual_screws','normal']:
  rs=[r for r in rows if r['group']==group];summary[group]=dict(total=len(rs),kept=sum(r['new']['keep'] for r in rs),wrong=[r['number'] for r in rs if not r['correct']])
 summary['focus_wire']=dict(number=10,false_alarm=rows[9]['new']['keep'])
 save(OUT/'summary.json',summary)
 assert all(sha(Path(p))==h for p,h in protected.items())
 save(OUT/'preservation.json',dict(protected_files=len(protected),unchanged=True,production_changes=False))
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
