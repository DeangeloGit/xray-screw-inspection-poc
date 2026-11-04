"""Fixed-input recognition tests. Does not alter production models or crops."""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from dino_adapter import input_image
OUT=ROOT/'workspace/dino-fixed-crop-recognition-20261103'
MODEL=ROOT/'models/dino-paired-47-20261103'
PRIOR=ROOT/'workspace/added-object-pilot-20261103'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):return v/max(np.linalg.norm(v),1e-12)
def main():
 import onnxruntime as ort
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json');plan=read(PRIOR/'plan.json')
 ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 overlap=[i for i,k in enumerate(ids) if k.removesuffix('.png') in {z['key'] for z in plan['cases']}]
 rules=dict(fixed_test_inputs='Original production candidate +12, frozen 224x224 DINO images; never recenter.',
  variants=['original_cls','eight_views_cls','patch_mean','eight_views_patch_mean'],
  example_views='0,90,180,270 degrees; same four after horizontal flip; lossless full-image transforms',
  voting='For augmented methods max similarity per original example across its 8 views; then top3 distinct original examples per class. Each original example contributes once.',
  patch='L2 normalize mean of raw 256 patch tokens, ignoring CLS; no object mask or region selection.',
  threshold=0,keep='target screw AND reference non_screw',test_cases=[z['key'] for z in plan['cases']],
  excluded_known_overlap=[ids[i] for i in overlap],parameters_selected_before_results=True)
 save(OUT/'rules.json',rules)
 protected=[p for p in MODEL.rglob('*') if p.is_file()]+[ROOT/'models/active.json']+[ROOT/f for f in ['detector.py','dino_adapter.py','acquisition.py','library.py','static/user.js']]
 for z in plan['cases']:protected += [Path(z['source'])/f for f in ['reference.png','aligned.png','result.json']]
 before={str(p):sha(p) for p in protected};save(OUT/'preservation-before.json',before)
 cachefile=OUT/'features.npz';cache=dict(np.load(cachefile)) if cachefile.exists() else {}
 opt=ort.SessionOptions();opt.intra_op_num_threads=4
 session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opt,providers=['CPUExecutionProvider'])
 def features(im):
  key=hashlib.sha256(im.tobytes()).hexdigest()
  if key not in cache:
   a=np.asarray(im,dtype=np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
   raw=session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0]
   cache[key]=np.stack([norm(raw[0]),norm(raw[1:].mean(axis=0))])
  return cache[key],key
 banks=[]
 for i,k in enumerate(ids):
  im=Image.open(MODEL/'examples'/meta[k]['file']).convert('L');inp=input_image(m,np.asarray(im,dtype=np.float32)/255)
  views=[]
  for flip in [False,True]:
   a=inp.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else inp
   for angle in [0,90,180,270]:views.append(features(a.rotate(angle))[0])
  views=np.stack(views);expected=np.asarray(m['example_bank']['screw' if labels[i] else 'normal']['embeddings'][i if i<47 else i-47])
  assert np.allclose(views[0,0],expected,atol=2e-5),(k,float(np.max(np.abs(views[0,0]-expected))))
  banks.append(views)
  if i%14==0:print('example',i+1,'/112',flush=True);np.savez(cachefile,**cache)
 bank=np.stack(banks);np.savez(OUT/'bank-features.npz',bank=bank)
 rows=[]
 def classify(v,kind,include):
  token=1 if 'patch' in kind else 0
  sims=bank[:,:,token]@v[token]
  scores=sims.max(axis=1) if 'eight' in kind else sims[:,0]
  evidence={}
  for name,mask in [('screw',labels),('normal',~labels)]:
   ix=np.where(mask&include)[0];best=ix[np.argsort(scores[ix])[-3:][::-1]]
   evidence[name]=dict(similarity=float(scores[best].mean()),neighbors=[dict(id=ids[j],similarity=float(scores[j]),view=int(np.argmax(sims[j])) if 'eight' in kind else 0) for j in best])
  margin=evidence['screw']['similarity']-evidence['normal']['similarity']
  return dict(screw=margin>=0,margin=margin,evidence=evidence)
 for n,z in enumerate(plan['cases'],1):
  vectors={};hashes={}
  for side in ['reference','target']:
   im=Image.open(PRIOR/'images'/f'{n}-dino-{side}.png').convert('RGB')
   assert im.size==(224,224)
   # Reconstruct the production crop and confirm frozen input equality.
   c=z['c'];full=Image.open(Path(z['source'])/('reference.png' if side=='reference' else 'aligned.png')).convert('L')
   x,y,w,h=[c[k] for k in ['x','y','w','h']]
   reconstructed=input_image(m,np.asarray(full.crop((max(0,x-12),max(0,y-12),min(full.width,x+w+12),min(full.height,y+h+12))),dtype=np.float32)/255)
   assert im.tobytes()==reconstructed.tobytes()
   im.save(OUT/'images'/f'{n}-{side}.png');vectors[side],hashes[side]=features(im)
  rec=dict(number=n,key=z['key'],name=z['name'],machine=z['machine'],category=z['category'],expected=z['expected'],input_hashes=hashes,protocols={})
  for protocol,include in [('all_47_65',np.ones(112,bool)),('exclude_known_overlap',~np.isin(np.arange(112),overlap))]:
   rec['protocols'][protocol]={}
   for kind in rules['variants']:
    pair={side:classify(v,kind,include) for side,v in vectors.items()};pair['keep']=pair['target']['screw'] and not pair['reference']['screw']
    rec['protocols'][protocol][kind]=pair
  rows.append(rec)
 np.savez(cachefile,**cache);save(OUT/'results.json',rows)
 summary={}
 for protocol in ['all_47_65','exclude_known_overlap']:
  summary[protocol]={}
  for kind in rules['variants']:
   pairs=[r['protocols'][protocol][kind] for r in rows]
   summary[protocol][kind]=dict(screw_pairs_correct=sum(p['keep'] for p in pairs[:2]),
    screw_pair_labels=[dict(reference=p['reference']['screw'],target=p['target']['screw']) for p in pairs[:2]],
    normal_alerts=[i+1 for i,p in enumerate(pairs) if i>=2 and p['keep']],
    normal_both_non_screw=sum(not p['reference']['screw'] and not p['target']['screw'] for p in pairs[2:]))
 save(OUT/'summary.json',summary)
 assert all(sha(Path(p))==v for p,v in before.items())
 save(OUT/'preservation.json',dict(files=len(before),unchanged=True,formal_changes=False))
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
