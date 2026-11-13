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
    ap.add_argument('--resume-from',type=Path)
    ap.add_argument('--cases',help='Comma-separated exact case keys; omitted means all')
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
    original=ModelManager(lean/'models',allow_cpu=True,execution_override='cpu').snapshot()
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
    import cv2,itertools
    cv2.setNumThreads(4)
    from alarm_review5r import review_alarm
    from correspondence_stability_probe import variations
    cases=read(trial/'screen-cases.json')
    for z in read(ROOT/'workspace/dino-4r-stability-20261106/perturbation-results.json')['pairs']:
        for side in ['kept','excluded']:
            cid=int(z['pair'][side].split('-')[1]);photo='ng-'+z['pair']['photo']
            cases.append(dict(key='conflict-'+photo+'-'+str(cid),folder=str(ROOT/'workspace/dino-4r-crossbatch-20261106/runs'/photo),id=cid,expected='consistency'))
    for cid in [22,40]:cases.append(dict(key='connector-'+str(cid),folder=str(ROOT/'workspace/dino-4r-crossbatch-20261106/runs/ng-128'),id=cid,expected='exclude'))
    if a.cases:
        selected=set(a.cases.split(','));assert selected<={c['key'] for c in cases}
        cases=[c for c in cases if c['key'] in selected]
    save(out/'plan.json',dict(runner_sha256=sha(__file__),core_policy_sha256=sha(ROOT/'experiments/dino/local_object5r.py'),alarm_policy_sha256=sha(ROOT/'experiments/dino/alarm_review5r.py'),cases=cases,trial_main_sha256=sha(trial/'main-trial.npz'),trial_part_sha256=sha(trial/'part-trial.npz'),scope='Candidate jitter and scaled frozen support; no proposal regeneration',production_changed=False))
    manifest=copy.deepcopy(original.manifest);manifest['example_bank']['screw']['ids']=ids[:n];manifest['example_bank']['normal']['ids']=ids[n:]
    new_manifest=copy.deepcopy(original.manifest);new_manifest['example_bank']['screw']['ids']=trial_ids[:trial_n];new_manifest['example_bank']['normal']['ids']=trial_ids[trial_n:]
    rows=[]
    if a.resume_from:
        previous=read(a.resume_from/'plan.json');current=read(out/'plan.json')
        for k in ['cases','core_policy_sha256','alarm_policy_sha256','trial_main_sha256','trial_part_sha256']:assert previous[k]==current[k],k
        rows=read(a.resume_from/'results.json');save(out/'resumed.json',dict(source=str(a.resume_from),results_sha256=sha(a.resume_from/'results.json'),completed_cases=len(rows)))
    completed={r['key'] for r in rows};fresh_objects=policy.Objects
    for case in cases:
        if case['key'] in completed:continue
        folder=Path(case['folder']);r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']);seed=next(c for c in cs if c['id']==case['id']);arrays=[]
        for name in ['reference','aligned']:
            with Image.open(folder/(name+'.png')) as im:arrays.append(np.asarray(im.convert('L'),np.float32)/255)
        session=TensorCache(original.session,original.identity,limit=1800);old=replace(original,manifest=manifest,feature_bank=bank,session=session);new=replace(original,manifest=new_manifest,feature_bank=trial_bank,session=session)
        geometry_cache={}
        def exact_geometry(ref,tar,support):
            key=(id(ref),id(tar),id(support))
            if key not in geometry_cache:geometry_cache[key]=(ref,tar,support,fresh_objects(ref,tar,support))
            obj=geometry_cache[key][3];obj.old_kept=[]
            return obj
        policy.Objects=exact_geometry
        def run(ref,tar,q,support):
            policy.configure(part,config,review);obj=policy.Objects(ref,tar,support);pred=integrated.classify(old,ref,tar,q,obj);pred,_=terminal.apply(old,ref,tar,pred,review,normal)
            policy.configure(part_trial,config,review);after=review_alarm(new,ref,tar,pred,q,support,review,normal,core_snapshot=old)
            return pred,after
        before,after=run(*arrays,seed,cs);expected=after['filter_recommendation'];extent=after['canonical_object']['box'];jitter=[];scales=[]
        for change,settings in variations(seed):
            q=dict(seed,**change)
            try:bp,p=run(*arrays,q,cs)
            except ValueError as exc:
                if str(exc) not in ('No image-derived exposed part supports this query','No image object supports this candidate window'):raise
                jitter.append(dict(**settings,baseline_unsupported=True,consistent=None,error=str(exc)));continue
            jitter.append(dict(**settings,before=bp['filter_recommendation'],after=p['filter_recommendation'],box=p['canonical_object']['box'],consistent=p['filter_recommendation']==expected and p['canonical_object']['box']==extent))
        for scale in [.75,.9,1.,1.1,1.25]:
            rr,tt=[cv2.resize(a,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC).clip(0,1) for a in arrays];support=[]
            for c in cs:
                q=copy.deepcopy(c)
                for k in ['x','y','w','h']:q[k]=max(1,round(c[k]*scale))
                q['area']=round(q['area']*scale*scale)
                if q.get('visible_part'):
                    for k in ['box','occluder_box']:
                        if k in q['visible_part']:q['visible_part'][k]=[round(v*scale) for v in q['visible_part'][k]]
                support.append(q)
            q=next(c for c in support if c['id']==case['id'])
            try:bp,p=run(rr,tt,q,support)
            except ValueError as exc:
                if str(exc) not in ('No image-derived exposed part supports this query','No image object supports this candidate window'):raise
                scales.append(dict(scale=scale,baseline_unsupported=True,new_loss=False,error=str(exc)));continue
            scales.append(dict(scale=scale,before=bp['filter_recommendation'],after=p['filter_recommendation'],new_loss=case['expected']=='keep' and bp['filter_recommendation']=='keep' and p['filter_recommendation']!='keep',expected_original=case['expected'],paired_evidence=p['paired_evidence']))
        row=dict(key=case['key'],expected=case['expected'],baseline=before['filter_recommendation'],trial=expected,jitter=jitter,scales=scales);rows.append(row);save(out/'results.json',rows)
        print(case['key'],'jitter',sum(v['consistent'] is True for v in jitter),'/',len(jitter),'scale losses',[v['scale'] for v in scales if v['new_loss']],flush=True)
    save(out/'summary.json',dict(cases=len(rows),jitter_tests=sum(len(r['jitter']) for r in rows),jitter_failures=[dict(key=r['key'],test=v) for r in rows for v in r['jitter'] if v['consistent'] is False],baseline_unsupported_queries=[dict(key=r['key'],test=v) for r in rows for v in r['jitter'] if v.get('baseline_unsupported')],new_scale_losses=[dict(key=r['key'],test=v) for r in rows for v in r['scales'] if v['new_loss']],scope='Frozen-support tests only; reused exact tensors and image/support-identical geometry with old_kept reset between independent trials. Visible proposal metadata scaled, not re-detected.',activation_allowed=False,production_changed=False))

if __name__=='__main__':main()
