"""Learn a small classifier from the112 bank examples only. Frozen59 test cases."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import read,save,sha,MODEL
OLD=ROOT/'workspace/dino-fixed-crop-recognition-20261103'
EXTRA=ROOT/'workspace/dino-unseen-equal-pair-20261103'
OUT=ROOT/'workspace/dino-learn-joint-20261103'

def kernel(x,z,kind,gamma):
 if kind=='linear':return x@z.T
 d=np.maximum(0,(x*x).sum(1)[:,None]+(z*z).sum(1)[None,:]-2*x@z.T)
 return np.exp(-gamma*d)

def prepare_fit(x,y,kind,gamma):
 # Balanced classes; weights total n, with each image contributing equal 8 views.
 weights=np.where(y>0,.5/(y>0).sum(),.5/(y<0).sum())*len(y)
 sw=np.sqrt(weights);p=weights/weights.sum();k=kernel(x,x,kind,gamma)
 km=k@p;mean=float(p@km);kc=k-km[:,None]-km[None,:]+mean
 values,vectors=np.linalg.eigh(sw[:,None]*kc*sw[None,:]);my=float(p@y)
 rhs=vectors.T@(sw*(y-my))
 return dict(x=x,sw=sw,p=p,km=km,mean=mean,values=values,vectors=vectors,rhs=rhs,my=my,kind=kind,gamma=gamma)

def coefficients(f,penalty):return f['sw']*(f['vectors']@(f['rhs']/(np.maximum(f['values'],0)+penalty)))
def score(f,alpha,z):
 k=kernel(z,f['x'],f['kind'],f['gamma']);kc=k-(k@f['p'])[:,None]-f['km'][None,:]+f['mean']
 return kc@alpha+f['my']

def main():
 OUT.mkdir(exist_ok=True)
 m=read(MODEL/'manifest.json');bank=np.load(OLD/'bank-features.npz')['bank'].astype('float64')
 ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids'];labels=np.r_[np.ones(47),-np.ones(65)]
 assert bank.shape==(112,8,2,384)
 x=bank.reshape(112,8,768)/np.sqrt(2)
 group_folds=np.r_[np.arange(47)%5,np.arange(65)%5]
 d=np.maximum(0,2-2*x[:,0]@x[:,0].T);gamma=1/float(np.median(d[np.triu_indices(112,1)]))
 rule=dict(bank=[47,65],input='Exact existing production224 images; no crop or threshold changes',
  features='Concatenate normalized DINO CLS and mean patch features, then divide by sqrt2',
  classifiers=['linear','rbf'],penalties=[.01,.1,1.,10.,100.],rbf_gamma=gamma,
  training_views='All8 saved rotations/mirrors per original bank example',
  selection='5fold stratified group CV on112 examples only; all8 transformations of same example stay in same fold. Score original orientation of heldout images. Minimize balanced error; tie fewer normal false alarms, linear first, larger penalty.',
  fold_by_original_example=group_folds.tolist(),threshold=0,
  test='original2 + additional57; no test image used to fit or select parameters',
  expected_five='Assistant re-reviewed reference/target pairs and expects added screws at all5 prior suspect positions. Treat all5 failures as wrong against this explicit visual expectation, keep source separate from user-confirmed labels.',
  limitation='Same known development cases. Bank examples can share montage source; bank CV is grouped by example, not verified physical screw or source photo.')
 save(OUT/'rules.json',rule)
 protected=read(EXTRA/'preservation-before.json')
 protected.update({str(p):sha(p) for p in [OLD/'results.json',OLD/'equal-vote-results.json',OLD/'features.npz',OLD/'bank-features.npz',EXTRA/'results.json',EXTRA/'features.npz']})
 assert all(sha(Path(p))==h for p,h in protected.items())
 save(OUT/'preservation-before.json',protected)
 trials=[]
 for kind in rule['classifiers']:
  predicted={p:np.zeros(112) for p in rule['penalties']}
  for fold in range(5):
   train=group_folds!=fold;test=~train;f=prepare_fit(x[train].reshape(-1,768),np.repeat(labels[train],8),kind,gamma)
   for penalty in rule['penalties']:predicted[penalty][test]=score(f,coefficients(f,penalty),x[test,0])
   print('bank validation',kind,'fold',fold+1,'/5',flush=True)
  for penalty,preds in predicted.items():
   misses=int(((preds<0)&(labels>0)).sum());false=int(((preds>=0)&(labels<0)).sum())
   trials.append(dict(kind=kind,penalty=penalty,screw_misses=misses,normal_false_alarms=false,balanced_error=.5*(misses/47+false/65),validation_scores=preds.tolist()))
 chosen=min(trials,key=lambda r:(r['balanced_error'],r['normal_false_alarms'],r['kind']!='linear',-r['penalty']))
 save(OUT/'training.json',dict(trials=trials,chosen=chosen))
 print('selected before test',chosen['kind'],chosen['penalty'],chosen['screw_misses'],chosen['normal_false_alarms'],flush=True)
 # Fit selected classifier on full112 examples; serialize before reading test outcomes.
 f=prepare_fit(x.reshape(-1,768),np.repeat(labels,8),chosen['kind'],gamma);alpha=coefficients(f,chosen['penalty'])
 np.savez(OUT/'classifier.npz',train_x=f['x'],alpha=alpha,p=f['p'],km=f['km'],mean=f['mean'],intercept=f['my'],gamma=gamma)
 cache=dict(np.load(OLD/'features.npz'));cache.update(dict(np.load(EXTRA/'features.npz')))
 old=read(OLD/'results.json')[:2];equal=read(OLD/'equal-vote-results.json')[:2];extra=read(EXTRA/'results.json');ep=read(EXTRA/'plan.json')['cases'];source=read(ROOT/'workspace/added-object-pilot-20261103/plan.json')['cases'][:2]
 tests=[]
 for i,(r,e,z) in enumerate(zip(old,equal,source)):
  tests.append(dict(key=r['key'],name=r['name'],id=z['id'],group='original_screw',source=z['source'],c=z['c'],input_hashes=r['input_hashes'],
   baseline=r['protocols']['all_47_65']['original_cls'],equal=e['protocols']['all_47_65'],image_base=str(OLD/'images'/str(i+1)),context=str(ROOT/f'workspace/added-object-pilot-20261103/images/{i+1}-pair.jpg')))
 for i,(r,z) in enumerate(zip(extra,ep),1):
  tests.append(dict(key=r['key'],name=r['name'],id=z['id'],group='extra_confirmed' if r['group']=='confirmed_screw' else 'five_visual_screws' if r['group']=='suspected_screw' else 'normal',
   source=z['source'],c=z['c'],input_hashes={s:v['input_sha256'] for s,v in r['audit'].items()},
   baseline={**{s:r['pair'][s]['original'] for s in ['reference','target']},'keep':r['keep']['original']},
   equal={**{s:r['pair'][s]['equal'] for s in ['reference','target']},'keep':r['keep']['equal']},image_base=str(EXTRA/'images'/str(i)),context=str(EXTRA/'images'/f'{i}-pair.jpg'),
   category=r['category'],machine=r['machine']))
 results=[]
 for i,z in enumerate(tests,1):
  pair={}
  for side,key in z['input_hashes'].items():
   val=float(score(f,alpha,(cache[key].reshape(1,768)/np.sqrt(2)).astype('float64'))[0]);pair[side]=dict(screw=val>=0,score=val)
  pair['keep']=pair['target']['screw'] and not pair['reference']['screw']
  results.append(dict(number=i,**z,new=pair,correct=not pair['keep'] if z['group']=='normal' else pair['keep']))
 summary={}
 for group in ['original_screw','extra_confirmed','five_visual_screws','normal']:
  rs=[r for r in results if r['group']==group];summary[group]=dict(total=len(rs),baseline_kept=sum(r['baseline']['keep'] for r in rs),equal_kept=sum(r['equal']['keep'] for r in rs),new_kept=sum(r['new']['keep'] for r in rs),new_wrong=[r['number'] for r in rs if not r['correct']])
 wire=next(r for r in results if r['key']==extra[7]['key']);summary['focus_wire']=dict(number=wire['number'],old_false_alarm=wire['equal']['keep'],new_false_alarm=wire['new']['keep'])
 save(OUT/'results.json',results);save(OUT/'summary.json',summary)
 assert all(sha(Path(p))==h for p,h in protected.items())
 save(OUT/'preservation.json',dict(protected_files=len(protected),unchanged=True,model_bank_47_65_unchanged=True,production_changes=False))
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
