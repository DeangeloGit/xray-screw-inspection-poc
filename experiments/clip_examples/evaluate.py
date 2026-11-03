import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from model_manager import ModelManager
WORK=ROOT/'workspace/windows-check';OUT=WORK/'diagnostics/clip-screw-examples'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
snap=ModelManager(ROOT/'models',allow_cpu=True).snapshot('clip-shape-4bf2386067d8');assert not snap.error
m=snap.manifest
cache={}
def encode(image):
 im=image.convert('RGB');w,h=im.size;size=(224,int(224*h/w)) if w<=h else (int(224*w/h),224);im=im.resize(size,Image.Resampling.BICUBIC);l,t=(im.width-224)//2,(im.height-224)//2
 a=(np.asarray(im.crop((l,t,l+224,t+224)),np.float32)/255-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
 v=snap.session.run(None,{snap.session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];return v/np.linalg.norm(v)
items=[]
for c in read(OUT/'examples.json'):
 im=Image.open(OUT/c['file'])
 if min(im.size)<16:continue
 items.append(dict(name=c['id'],label='screw',split=c['split'],vector=encode(im).tolist()))
batch=WORK/'diagnostics/v10-full-evaluation-20261103'
for row in read(batch/'results.json'):
 if row['is_reference'] or row['label']!='OK':continue
 folder=batch/'photos'/row['sha256'];result=read(folder/'result.json');im=Image.open(folder/'aligned.png')
 for c in result['candidates']:
  x,y,w,h=(c[k] for k in ('x','y','w','h'));patch=im.crop((max(0,x-12),max(0,y-12),min(im.width,x+w+12),min(im.height,y+h+12)))
  wire='15_53_47_24' in row['path'] and c['id']==1
  split='validation' if wire or int(row['sha256'][:2],16)%2 else 'bank'
  name=row['sha256']+'-'+str(c['id']);patch.save(OUT/(name+'.png'))
  items.append(dict(name=name,label='normal',split=split,wire=wire,old=c['classification'],vector=encode(patch).tolist()))
old=read(WORK/'ai-trials/clip-tight-results/report.json')
for sample in old['samples']:
 for i in {i for z in sample['known_regions'] for i in z['candidate_ids']}:
  im=Image.open(WORK/f'ai-trials/clip-tight-results/{sample["name"]}/crop_{i}.png')
  items.append(dict(name=sample['name']+'-'+str(i),label='known_screw',split='validation',vector=encode(im).tolist()))
(OUT/'features.json').write_text(json.dumps(items))
pos=np.asarray([z['vector'] for z in items if z['split']=='bank' and z['label']=='screw']);neg=np.asarray([z['vector'] for z in items if z['split']=='bank' and z['label']=='normal'])
for c in items:
 if c['split']!='validation':continue
 v=np.asarray(c['vector']);p=np.sort(pos@v)[-3:].mean();n=np.sort(neg@v)[-3:].mean();c['margin']=float(p-n);c['positive_similarity']=float(p)
 if c['label']=='known_screw' or c.get('wire'):print(c['name'],c['label'],round(p,4),round(n,4),round(p-n,4))
for label in ['screw','normal','known_screw']:
 vals=[c['margin'] for c in items if c['split']=='validation' and c['label']==label];print(label,len(vals),'margin',np.round(np.percentile(vals,[0,25,50,75,100]),4))
(OUT/'features.json').write_text(json.dumps(items))
