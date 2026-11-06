"""Freeze reviewed scoring corrections and photo-disjoint example experiment."""
import copy,json,hashlib,os,sys
from pathlib import Path
import numpy as np,cv2
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
BASE=ROOT/'workspace/dino-4r-correspondence-20261106/final'
OUT=ROOT/'workspace/dino-4r-blackblock-20261106';OUT.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from answered_batch_report import native,matches
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
answers=copy.deepcopy(read(BASE/'answers.json'));changes=[]
for photo,mid,cid,extent in [('133',3,18,None),('135',1,88,[1365,669,15,17]),('137',6,65,None),('130',10,5,None),('128',11,10,None)]:
    r=read(BASE/'runs/pilot'/photo/'result.json');c=copy.deepcopy(next(c for c in r['candidates']+r['filtered_candidates'] if c['id']==cid))
    arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{photo}.npz');flow=np.zeros((*arr['ref'].shape,2),np.float32)
    for reg in r['local_alignment']:
        x,y,X,Y=reg['bbox'];flow[y:Y,x:X]=[reg['dx'],reg['dy']]
    flow=cv2.GaussianBlur(flow,(0,0),12)
    if extent:c['classification']['canonical_object']['box']=extent
    poly=native(c,r,flow);old=next((m for m in answers[photo]['marks'] if m['id']==mid),None)
    corrected=dict(old or {},id=mid,polygon=poly.tolist(),center=poly.mean(axis=0).tolist(),reviewed_correction=True)
    if old:answers[photo]['marks'][answers[photo]['marks'].index(old)]=corrected
    else:answers[photo]['marks'].append(corrected)
    changes.append(dict(photo=photo,answer_id=mid,candidate_reference=cid,old=old,new=corrected,authority='使用者確認線材掉落螺絲、接受其餘診斷並授權校正評分；原圖及原答案不變',scope='evaluation_only_not_runtime_input'))
save(OUT/'answers-original.json',read(BASE/'answers.json'));save(OUT/'answers-corrected.json',answers);save(OUT/'scoring-corrections.json',changes)
cases=read(BASE/'cases.json');marks=[]
for photo,a in answers.items():
    for m in a['marks']:
        yes=[c['key'] for c in cases if c['photo']==photo and c['keep']['pilot'] and m['id'] in matches(c['native'],[m])[0]]
        marks.append(dict(photo=photo,id=m['id'],hit=bool(yes),candidates=yes))
original_hits={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']}
hits={(m['photo'],m['id']) for m in marks if m['hit']};assert original_hits<=hits
assert ('128',11) in hits and ('135',1) in hits
plan=read(BASE/'plan.json');training=['128','131','132'];heldout=['129','130','133','134','135','136','137'];examples=[]
for photo in training:
    cs=[c for c in cases if c['photo']==photo and 10 in c['answers']]
    assert len(cs)==1
    examples.append(dict(photo=photo,candidate_id=cs[0]['id'],box=cs[0]['canonical_object']['box'],label='screw',source_answer_id=10))
freeze=dict(base=str(BASE),model=plan['model'],training_photos=training,heldout_photos=heldout,added_examples=examples,crop_original='candidate rectangle +12; current model center crop',crop_alternative='square centered on full candidate; side=max(w,h)+8',bank_original='47 screw +65 normal',bank_alternative='original 47 screw +3 training-photo big-block examples + original65 normal',threshold=0,selection='retain baseline unless all 55 old hits, both user-confirmed screws, all corrected baseline hits retained and unmatched alarms do not increase overall or per photo',independence='Only NEW examples use disjoint photos. Same previously used scan corpus, similar physical layout; not independent acceptance.',protected_hashes=plan['hashes'])
save(OUT/'experiment-plan.json',freeze);save(OUT/'corrected-baseline.json',dict(answers=len(marks),hits=len(hits),original_hits_preserved=True,two_user_confirmed_preserved=True,marks=marks))
print('Corrected baseline',len(hits),'/',len(marks),'protected old',len(original_hits),'examples',examples)
