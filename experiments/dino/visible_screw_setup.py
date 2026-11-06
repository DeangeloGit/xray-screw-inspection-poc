"""Separate B-part evaluation annotation from untouched original answer images."""
import os,sys,json,copy
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));BASE=ROOT/'workspace/dino-4r-blackblock-20261106/final';OUT=ROOT/'workspace/dino-4r-visible-screw-20261106/v2';FINAL=OUT/'final';FINAL.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from answered_batch_report import read,save,native,matches
answers=copy.deepcopy(read(BASE/'answers.json'));changes=[];plan=read(BASE/'plan.json');overlay=FINAL/'reviewed-answer-images';overlay.mkdir(exist_ok=True)
for row in plan['items']:
    key=row['key']
    if key=='golden':continue
    r=read(BASE/'runs/pilot'/key/'result.json');c=copy.deepcopy(next(c for c in r['filtered_candidates'] if c['classification']['canonical_object']['box'][0] in (703,704,705) and 430<c['y']<450 and c['h']>25))
    a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{key}.npz');flow=np.zeros((*a['ref'].shape,2),np.float32)
    for reg in r['local_alignment']:
        x,y,X,Y=reg['bbox'];flow[y:Y,x:X]=[reg['dx'],reg['dy']]
    flow=cv2.GaussianBlur(flow,(0,0),12);c['classification']['canonical_object']['box']=[727,440,10,21];poly=native(c,r,flow);old=next(m for m in answers[key]['marks'] if m['id']==10);new=dict(old,polygon=poly.tolist(),center=poly.mean(axis=0).tolist(),reviewed_correction=True,semantic_part='B exposed screw')
    answers[key]['marks'][answers[key]['marks'].index(old)]=new;changes.append(dict(photo=key,answer_id=10,old=old,new=new,authority='使用者確認128的B；其餘9張由助理逐張檢視相同部位，不冒稱人工逐點標註',aligned_review_box=[727,440,10,21],runtime_uses_answer=False))
    im=Image.open(row['path']).convert('RGB');d=ImageDraw.Draw(im)
    for m in answers[key]['marks']:
        pts=[tuple(p) for p in m['polygon']];d.line(pts+[pts[0]],fill='red',width=5);d.text(tuple(m['center']),str(m['id']),fill='red',stroke_width=2)
    path=overlay/f'{key}.png';im.save(path);row['previous_answer']=row['answer'];row['answer']=str(path)
save(OUT/'answers-B-reviewed.json',answers);save(OUT/'B-annotation-changes.json',changes);save(OUT/'reviewed-plan.json',plan)
cs=read(BASE/'cases.json');hits={(c['photo'],i) for c in cs if c['keep']['pilot'] for i in matches(c['native'],answers.get(c['photo'],{}).get('marks',[]))[0]};oldhits={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']};assert hits==oldhits and len(hits)==59
print('B annotation leaves baseline',len(hits),'unchanged; original source labels untouched')
