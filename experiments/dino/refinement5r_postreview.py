"""Isolated 5r regression guards using frozen experimental banks. Never activates a bank.

The first gate is selected-candidate replay with complete proposal support,
not a full detector/corpus acceptance. Any lost protected detection rejects
the arm before expensive whole-corpus validation.
"""
import argparse,copy,hashlib,json,os,sys
from pathlib import Path
from dataclasses import replace
from collections import OrderedDict

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/dino')]

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--probe',type=Path,required=True)
    ap.add_argument('--trial',type=Path,required=True)
    ap.add_argument('--guard',type=Path,required=True)
    ap.add_argument('--provider',choices=['cpu','gpu'],default='cpu')
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'plan.json').exists():raise ValueError('Refusing to overwrite an experiment plan')
    assert read(a.probe)['status']=='passed'
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated.json')
    import numpy as np
    from PIL import Image,ImageDraw
    from model_manager import ModelManager
    import dino_paired_optimized as dino
    import example_audit_policy as policy
    import integrated_bank_policy as integrated
    import connector_policy as terminal
    from visible_screw_geometry_v2 import part_image
    from new_model_run import TensorCache
    lean=ROOT/'workspace/handoffs/20261109-lean/station'
    arc=lean/'archives/workspace'
    original=ModelManager(lean/'models',allow_cpu=True,execution_override=a.provider).snapshot()
    if original.error or original.session is None:raise ValueError('Formal model unavailable')
    vr=ROOT/'workspace/5r-live/example-versions';vr=vr/read(vr/'active.json')['version'];meta=read(vr/'version.json')
    assert sha(vr/'bank.npz')==meta['bank_sha256']
    for row in meta['examples']:assert sha(vr/row['file'])==row['sha256']
    bank=np.load(vr/'bank.npz')['bank'];ids=[x['id'] for x in meta['examples']];n=sum(x['label']=='screw' for x in meta['examples'])
    partroot=arc/'dino-4r-visible-screw-20261106'
    part=np.load(partroot/'visible-part-bank.npz')['bank'];config=read(partroot/'v3/experiment-plan.json')
    review=np.load(arc/'dino-4r-example-audit-20261106/letterbox-112-bank.npz')['bank']
    with np.load(arc/'dino-4r-connector-20261106/normal-connector-bank.npz') as z:
        normal=dict(bank=z['bank'].copy(),aspect=float(z['aspect']))
    trial=a.trial.resolve()
    with np.load(trial/'main-trial.npz') as z:
        trial_bank=z['bank'].copy();trial_n=int(z['n']);trial_ids=z['ids'].tolist()
    part_trial=np.load(trial/'part-trial.npz')['bank']
    assert np.array_equal(trial_bank[:n],bank[:n])
    assert np.array_equal(trial_bank[trial_n:trial_n+len(bank)-n],bank[n:])
    assert np.array_equal(part_trial[:len(part)],part)
    import cv2,time
    cv2.setNumThreads(4)
    from local_object5r import review_lost_keep
    import answered_batch_report as matching
    guard=read(a.guard/'summary.json')
    assert read(a.guard/'plan.json')['policy_sha256']==sha(ROOT/'experiments/dino/local_object5r.py')
    assert guard['arms']['with_local_core']['screen_passed'],'Protected-candidate gate has not passed'
    original_root=ROOT/'workspace/dino-4r-crossbatch-20261106'
    source_check=read(trial.parent/'original100-source-verification.json');assert source_check['status']=='passed' and source_check['count']==100
    original_items=read(original_root/'plan.json')['items'];answers=read(original_root/'answers.json')
    historic=read(ROOT/'workspace/dino-4r-integrated-bank-20261106/final/cases.json')
    expected={}
    for c in historic:
        if c['keep']:expected.setdefault(c['photo'],set()).update(c['answers'])
    items=[]
    for item in original_items:
        items.append(dict(item,folder=str(original_root/'runs'/item['key']),corpus='original100'))
    for batch_id in ['9c1f689b04d64536a0de3582270ca1ae','f2661437e1ce4ef19c5f10f107d35ab6']:
        batch=ROOT/'workspace/5r-live/folder-batches'/batch_id;job=read(batch/'job.json')
        for r in job['rows']:
            items.append(dict(key=job['label']+'-'+r['id'],folder=str(batch/'runs'/r['id']),corpus='KPH33-61',label=job['label'],machine='KPH33',path=str(Path(job['folder'])/r['file']),sha256=r['source_sha256'],training=r['id'] in {'000000','000003','000020','000040'} and job['label']=='OK'))
    priority=['OK-000001','OK-000008','OK-000009','OK-000015']
    items.sort(key=lambda r:(0 if r['key'] in priority else 1 if r['label']=='NG' else 2,r['key']))
    for item in items:
        if sha(item['path'])!=item['sha256']:raise ValueError('Source changed: '+item['key'])
    plan=dict(schema_version=1,runner_sha256=sha(__file__),policy_sha256=sha(ROOT/'experiments/dino/local_object5r.py'),probe_sha256=sha(a.probe),formal_model=original.info(),
        active_bank_sha256=sha(vr/'bank.npz'),trial_main_sha256=sha(trial/'main-trial.npz'),trial_part_sha256=sha(trial/'part-trial.npz'),
        items=items,scope='Postreview all existing alarms; prior exclusions copied byte-equivalently. Frozen original100 accepted baseline and current KPH33-61 results; no detector rerun',stop_on_first_regression=True,activation_allowed=False,production_changed=False)
    save(out/'plan.json',plan)
    from alarm_review5r import review_alarm
    plan['policy_sha256']=dict(local_object=sha(ROOT/'experiments/dino/local_object5r.py'),alarm_review=sha(ROOT/'experiments/dino/alarm_review5r.py'))
    save(out/'plan.json',plan)
    manifest=copy.deepcopy(original.manifest);manifest['example_bank']['screw']['ids']=trial_ids[:trial_n];manifest['example_bank']['normal']['ids']=trial_ids[trial_n:]
    rows=[]
    for item in items:
        started=time.perf_counter();folder=Path(item['folder']);r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']);arrays=[]
        for name in ['reference','aligned']:
            with Image.open(folder/(name+'.png')) as im:arrays.append(np.asarray(im.convert('L'),np.float32)/255)
        if item['corpus']=='original100':
            baseline_path=ROOT/'workspace/dino-4r-integrated-bank-20261106/replay'/item['key']/'curated_v5_review.json'
            baseline=read(baseline_path)['predictions']
        else:
            baseline_path=folder/'result.json';baseline={str(c['id']):c['classification'] for c in cs}
        assert set(baseline)=={str(c['id']) for c in cs}
        session=TensorCache(original.session,original.identity,limit=1800)
        snapshot=replace(original,manifest=manifest,feature_bank=trial_bank,session=session)
        core_manifest=copy.deepcopy(original.manifest);core_manifest['example_bank']['screw']['ids']=ids[:n];core_manifest['example_bank']['normal']['ids']=ids[n:]
        core_snapshot=replace(original,manifest=core_manifest,feature_bank=bank,session=session)
        policy.configure(part_trial,config,review)
        flow=np.zeros((*arrays[0].shape,2),np.float32)
        for z in r['local_alignment']:
            x,y,X,Y=z['bbox'];flow[y:Y,x:X]=[z['dx'],z['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12)
        result=copy.deepcopy(r);result['candidates']=[];result['filtered_candidates']=[]
        hits=set();baseline_hits=set();matches={};changed=[];excluded_equal=0;reviewed=0
        for c in cs:
            old=baseline[str(c['id'])]
            pred=review_alarm(snapshot,*arrays,old,c,cs,review,normal,core_snapshot=core_snapshot)
            if old['filter_recommendation']=='exclude':
                assert pred==old;excluded_equal+=1
            else:reviewed+=1
            assert pred['status']=='active'
            kept=pred['filter_recommendation']=='keep'
            assert not kept or old['filter_recommendation']=='keep'
            if kept != (old['filter_recommendation']=='keep'):changed.append(c['id'])
            cc=dict(c,classification=pred);result['candidates' if kept else 'filtered_candidates'].append(cc)
            if item['corpus']=='original100':
                yes,edge=matching.matches(matching.native(cc,r,flow),answers.get(item['key'],{}).get('marks',[]));matches[str(c['id'])]=yes
                if kept:hits.update(yes)
                if old['filter_recommendation']=='keep':
                    old_yes,_=matching.matches(matching.native(dict(c,classification=old),r,flow),answers.get(item['key'],{}).get('marks',[]));baseline_hits.update(old_yes)
        result['pre_ai_count']=len(cs);result['proposal_count']=len(result['candidates']);result['filtered_count']=len(result['filtered_candidates'])
        result['high_count']=sum(c['priority']=='high' for c in result['candidates']);result['review_count']=len(result['candidates'])-result['high_count'];result['wire_review_count']=sum(bool(c.get('wire_review')) for c in result['candidates'])
        result['experimental_policy']='5r alarm-only local review';result['production_changed']=False
        save(out/'runs'/item['key']/'result.json',result)
        lost_answers=sorted((baseline_hits|expected.get(item['key'],set()))-hits)
        lost_unconfirmed=changed if item['corpus']=='KPH33-61' and item['label']=='NG' else []
        row=dict(key=item['key'],label=item['label'],corpus=item['corpus'],candidates=len(cs),baseline_kept=reviewed,kept=len(result['candidates']),unchanged_exclusions=excluded_equal,changed_candidates=changed,answer_hits=sorted(hits),baseline_answer_hits=sorted(baseline_hits),matches=matches,lost_answers=lost_answers,lost_NG_unconfirmed=lost_unconfirmed,seconds=round(time.perf_counter()-started,2),baseline_sha256=sha(baseline_path),source_result_sha256=sha(folder/'result.json'))
        rows.append(row);save(out/'rows.json',rows);print('PHOTO',item['key'],'reviewed',reviewed,'lost',lost_answers,'kept',len(result['candidates']),'seconds',row['seconds'],flush=True)
        if lost_answers or lost_unconfirmed:
            save(out/'summary.json',dict(status='rejected',stopped_at=item['key'],completed_photos=len(rows),planned_photos=len(items),reason=row,full_corpus_completed=False,activation_allowed=False,production_changed=False));return
    save(out/'summary.json',dict(status='postreviewed',completed_photos=len(rows),planned_photos=len(items),candidates=sum(r['candidates'] for r in rows),reviewed_alarms=sum(r['baseline_kept'] for r in rows),kept=sum(r['kept'] for r in rows),unchanged_exclusions=sum(r['unchanged_exclusions'] for r in rows),full_corpus_completed=True,activation_allowed=False,production_changed=False,remaining_checks='Full report, stability and live detector integration are not accepted by this replay alone'))

if __name__=='__main__':main()
