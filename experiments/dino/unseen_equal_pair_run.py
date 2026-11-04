"""Frozen equal-vote method on pre-screened saved cases; no production changes."""
import sys,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.unseen_pair_prepare import OUT,BASE,FULL,MODEL,PRIOR,read,save
from experiments.dino.fixed_crop_recognition_pilot import norm,sha
from dino_adapter import input_image
PREV=ROOT/'workspace/dino-fixed-crop-recognition-20261103'

def main():
 import onnxruntime as ort
 pool=read(OUT/'screening-pool.json');m=read(MODEL/'manifest.json');meta=read(MODEL/'examples.json')
 # Frozen after image-only audit, before any scores from the new method.
 selected=[1,2,3,6,7,11,16]
 duplicates={4:46,5:33,8:43,9:32,10:45,13:39,15:40,17:42,18:44,19:43,20:47,21:44,22:44,23:46,24:42}
 positives=[]
 for n in selected:
  z=dict(pool['positive_review'][n-1]);z['screening_number']=n;z['group']='confirmed_screw' if z['known'] else 'suspected_screw';z['category']='unknown'
  z['label_basis']='既有螺絲標記' if z['known'] else '助手看參照／待測圖，列為疑似新增螺絲；非新增人工標籤'
  z['visual_provenance']='比對47張螺絲範例，未見同一裁圖；與16張拼圖範例的可見背景／姿態不同。拼圖缺原始檔名，不能完全證明來源獨立。'
  positives.append(z)
 normals=[]
 for n,item in enumerate(pool['normal_eligible'],1):
  z=dict(item);z['screening_number']=n;z['group']='normal';z['old_category']=z['category']
  if n in [1,2,3,29,34,41,49]:z['category']='wire'
  if n in [27,28,47]:z['category']='component'
  z['label_basis']='良品資料夾；外觀類型由助手核對本輪對照圖，非使用者逐框確認'
  z['visual_provenance']='來源照片不在65張正常範例的42個已知來源，也不在前輪17例已知來源；未見新增螺絲。'
  normals.append(z)
 cases=positives+normals
 ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
 bank=np.load(PREV/'bank-features.npz')['bank'];assert bank.shape==(112,8,2,384)
 expected=np.asarray(m['example_bank']['screw']['embeddings']+m['example_bank']['normal']['embeddings']);assert np.allclose(bank[:,0,0],expected,atol=2e-5)
 bank_hashes={}
 for k in ids:
  im=Image.open(MODEL/'examples'/meta[k]['file']).convert('L');inp=input_image(m,np.asarray(im,dtype=np.float32)/255)
  for flip in [False,True]:
   a=inp.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else inp
   for angle in [0,90,180,270]:bank_hashes.setdefault(hashlib.sha256(a.rotate(angle).tobytes()).hexdigest(),[]).append(k)
 source_hashes={p.name:sha(p) for p in [PREV/'equal-vote-rule.json',PREV/'bank-features.npz',MODEL/'manifest.json']}
 plan=dict(method=read(PREV/'equal-vote-rule.json'),method_source_hashes=source_hashes,full_bank=[47,65],selection_before_new_scores=True,
  selected_screw_review_numbers=selected,excluded_screw_review=[dict(number=z['number'],key=z['key'],reason='疑似與拼圖同源或高度相似，保守不列入',related_bank_number=duplicates.get(z['number'])) for z in pool['positive_review'] if z['number'] not in selected],
  cases=cases,scope='7 selected screw/suspected positions + all50 eligible OK candidates. Saved aligned crops only; no difference rerun or model/bank alteration.',
  limitation='Known metadata source exclusion + exact input hash + visual review. Montage16 has no original filenames; unseen-source independence is NOT fully verified. These cases were previously inspected under older models, not a pristine never-viewed holdout.')
 if (OUT/'plan.json').exists():assert read(OUT/'plan.json')==plan
 else:save(OUT/'plan.json',plan)
 protected=[p for p in MODEL.rglob('*') if p.is_file()]+[ROOT/'models/active.json']+[ROOT/f for f in ['detector.py','dino_adapter.py','acquisition.py','library.py','static/user.js']]
 for z in cases:protected += [Path(z['source'])/f for f in ['reference.png','aligned.png','result.json']]
 protected += [FULL/'cases.json',PREV/'equal-vote-rule.json',PREV/'bank-features.npz']
 before={str(p):sha(p) for p in protected};save(OUT/'preservation-before.json',before)
 cache=dict(np.load(PREV/'features.npz'));cp=OUT/'features.npz'
 if cp.exists():cache.update(dict(np.load(cp)))
 opt=ort.SessionOptions();opt.intra_op_num_threads=4
 session=ort.InferenceSession(str(MODEL/'model.onnx'),sess_options=opt,providers=['CPUExecutionProvider'])
 def features(im):
  key=hashlib.sha256(im.tobytes()).hexdigest()
  if key not in cache:
   a=np.asarray(im,dtype=np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
   raw=session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];cache[key]=np.stack([norm(raw[0]),norm(raw[1:].mean(axis=0))])
  return cache[key],key
 def compare(v):
  score_vectors={'original':bank[:,0,0]@v[0],'whole':(bank[:,:,0]@v[0]).max(axis=1),'local':bank[:,0,1]@v[1]}
  out={}
  for name,sc in score_vectors.items():
   ev={}
   for label,mask in [('screw',labels),('normal',~labels)]:
    ix=np.where(mask)[0];best=ix[np.argsort(sc[ix])[-3:][::-1]];ev[label]=dict(similarity=float(sc[best].mean()),neighbors=[ids[j] for j in best])
   margin=ev['screw']['similarity']-ev['normal']['similarity'];out[name]=dict(screw=margin>=0,margin=margin,evidence=ev)
  margin=(out['whole']['margin']+out['local']['margin'])/2;out['equal']=dict(screw=margin>=0,margin=margin)
  return out
 # Verify exactly same frozen arithmetic on all34 earlier inputs before new evaluation.
 prior_rows=read(PREV/'results.json');prior_equal=read(PREV/'equal-vote-results.json')
 for r,e in zip(prior_rows,prior_equal):
  for side,h in r['input_hashes'].items():
   p=compare(cache[h])
   assert abs(p['equal']['margin']-e['protocols']['all_47_65'][side]['margin'])<1e-6
 results=[];duplicates_seen=[]
 for i,z in enumerate(cases,1):
  c=z['c'];x,y,w,h=[c[k] for k in ['x','y','w','h']];pair={};audit={};crop_boxes={}
  for side,f in [('reference','reference.png'),('target','aligned.png')]:
   full=Image.open(Path(z['source'])/f).convert('L');box=[max(0,x-12),max(0,y-12),min(full.width,x+w+12),min(full.height,y+h+12)]
   im=input_image(m,np.asarray(full.crop(box),dtype=np.float32)/255);v,key=features(im);im.save(OUT/'images'/f'{i}-{side}.png')
   pair[side]=compare(v);audit[side]=dict(input_sha256=key,exact_bank_matches=sorted(set(bank_hashes.get(key,[]))));crop_boxes[side]=box
   if bank_hashes.get(key):duplicates_seen.append(dict(number=i,side=side,ids=audit[side]['exact_bank_matches']))
  keep={k:pair['target'][k]['screw'] and not pair['reference'][k]['screw'] for k in ['original','equal']}
  r=dict(number=i,key=z['key'],group=z['group'],machine=z['machine'],category=z['category'],name=z['name'],pair=pair,keep=keep,audit=audit,crop_boxes=crop_boxes)
  # Preserve and flag exact duplicates rather than silently selecting replacement cases.
  r['exact_target_overlap']=bool(audit['target']['exact_bank_matches']);results.append(r)
  if i%10==0:np.savez(cp,**cache);print('paired cases',i,'/',len(cases),flush=True)
 np.savez(cp,**cache);save(OUT/'results.json',results)
 summary={}
 for group in ['confirmed_screw','suspected_screw','normal']:
  subset=[r for r in results if r['group']==group and not r['exact_target_overlap']]
  summary[group]=dict(cases=len(subset),photos=len({r['name'] for r in subset}),original_kept=sum(r['keep']['original'] for r in subset),equal_kept=sum(r['keep']['equal'] for r in subset),
   new_alerts=[r['number'] for r in subset if r['keep']['equal'] and not r['keep']['original']],removed_alerts=[r['number'] for r in subset if r['keep']['original'] and not r['keep']['equal']])
 summary['all']=dict(cases=len(cases),photos=len({z['sha'] for z in cases}),exact_bank_input_matches=duplicates_seen,bank_screw=47,bank_normal=65,
   no_source_verified_independent_screw_claim=True,whole_batch_rerun=False,production_changes=False)
 save(OUT/'summary.json',summary)
 assert all(sha(Path(p))==v for p,v in before.items())
 save(OUT/'preservation.json',dict(files=len(before),unchanged=True,bank_47_65_unchanged=True,production_changes=False))
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
