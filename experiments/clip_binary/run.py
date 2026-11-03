"""Fixed-parameter offline linear probe. Never installs or activates a classifier."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from model_manager import ModelManager
WORK=ROOT/'workspace/windows-check';OUT=WORK/'diagnostics/clip-binary-probe';OUT.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
rows=read(WORK/'diagnostics/clip-screw-examples/features.json');train=[r for r in rows if r['split']=='bank'];test=[r for r in rows if r['split']=='validation']
x=np.asarray([r['vector'] for r in train]);y=np.asarray([r['label']=='screw' for r in train],float)
# Learn centering from the training partition only, with equal total class weights.
center=x.mean(axis=0);x=x-center;weight=np.where(y==1,.5/(y==1).sum(),.5/(y==0).sum())
w=np.zeros(x.shape[1]);b=0.;regularization=.01
for _ in range(2000):
 logits=np.clip(x@w+b,-30,30);prob=1/(1+np.exp(-logits));err=(prob-y)*weight
 w-=5*(x.T@err+regularization*w);b-=5*err.sum()
def predict(v):return float(1/(1+np.exp(-np.clip((np.asarray(v)-center)@w+b,-30,30))))
results=[]
for r in test:results.append(dict(name=r['name'],label=r['label'],score=predict(r['vector']),source='held-out-crop',wire=r.get('wire',False)))
snapshot=ModelManager(ROOT/'models',allow_cpu=True).snapshot('clip-examples-916f8a7fd458');m=snapshot.manifest
batch=WORK/'diagnostics/v11-examples-full-evaluation-20261103'
for z in read(batch/'visual-issues.json'):
 f=batch/'photos'/z['sha256'];r=read(f/'result.json');c=next(c for c in r['filtered_candidates'] if c['id']==z['candidate_id']);x0,y0,cw,ch=[c[k] for k in ['x','y','w','h']]
 with Image.open(f/'aligned.png') as image:im=image.crop((max(0,x0-12),max(0,y0-12),min(image.width,x0+cw+12),min(image.height,y0+ch+12))).convert('RGB')
 width,height=im.size;size=(224,int(224*height/width)) if width<=height else (int(224*width/height),224);im=im.resize(size,Image.Resampling.BICUBIC);left,top=(im.width-224)//2,(im.height-224)//2
 a=(np.asarray(im.crop((left,top,left+224,top+224)),np.float32)/255-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
 v=snapshot.session.run(None,{snapshot.session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];v/=np.linalg.norm(v)
 results.append(dict(name=z['relative']+' #'+str(z['candidate_id']),label='suspected_screw',score=predict(v),source='six-ng-visual-issues'))
summary={}
for label in ['normal','known_screw','screw','suspected_screw']:
 rs=[r for r in results if r['label']==label];summary[label]=dict(total=len(rs),kept=sum(r['score']>=.5 for r in rs),excluded=sum(r['score']<.5 for r in rs))
report=dict(activated=False,method='balanced logistic regression on frozen CLIP image features',threshold=.5,regularization=regularization,training_screws=int(y.sum()),training_normal=int(len(y)-y.sum()),summary=summary,results=results)
(OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');np.savez(OUT/'experimental-weights.npz',weight=w,bias=b,center=center)
print(json.dumps({k:v for k,v in report.items() if k!='results'}))
