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
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'plan.json').exists():raise ValueError('Refusing to overwrite an experiment plan')
    assert read(a.probe)['status']=='passed'
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated.json')
    import cv2
    cv2.setNumThreads(4)
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
    cases=read(trial/'screen-cases.json')
    seen={(Path(c['folder']).name,c['id']) for c in cases}
    for row in read(ROOT/'workspace/dino-4r-integrated-bank-20261106/final/cases.json'):
        if not row['keep'] or not row['answers'] or (row['photo'],row['id']) in seen:continue
        cases.append(dict(key=row['key'],folder=str(ROOT/'workspace/dino-4r-crossbatch-20261106/runs'/row['photo']),id=row['id'],label='historical_answer_matched',expected='keep',answer_ids=row['answers']))
        seen.add((row['photo'],row['id']))
    from local_object5r import review_lost_keep
    plan=dict(schema_version=1,runner_sha256=sha(__file__),policy_sha256=sha(ROOT/'experiments/dino/local_object5r.py'),
        probe_sha256=sha(a.probe),formal_model=original.info(),active_bank_sha256=sha(vr/'bank.npz'),
        trial_main_sha256=sha(trial/'main-trial.npz'),trial_part_sha256=sha(trial/'part-trial.npz'),
        inference_scope='Selected candidates with complete proposal support; not sequential full-photo acceptance',
        source_trial=str(trial),cases=cases,production_changed=False,activation_allowed=False)
    save(out/'plan.json',plan)
    session=TensorCache(original.session,original.identity,limit=1500);results=[]
    for case in cases:
        folder=Path(case['folder']);r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']);candidate=next(c for c in cs if c['id']==case['id'])
        arrays=[]
        for name in ['reference','aligned']:
            with Image.open(folder/(name+'.png')) as im:arrays.append(np.asarray(im.convert('L'),np.float32)/255)
        session.clear();row=dict(key=case['key'],label=case['label'],expected=case['expected'],arms={},source_result_sha256=sha(folder/'result.json'))
        for arm,main_bank,part_bank,selected_ids,selected_n in [('baseline',bank,part,ids,n),('combined',trial_bank,part_trial,trial_ids,trial_n)]:
            manifest=copy.deepcopy(original.manifest);manifest['example_bank']['screw']['ids']=selected_ids[:selected_n];manifest['example_bank']['normal']['ids']=selected_ids[selected_n:]
            snapshot=replace(original,manifest=manifest,feature_bank=main_bank,session=session)
            policy.configure(part_bank,config,review);objects=policy.Objects(*arrays,cs)
            pred=integrated.classify(snapshot,*arrays,candidate,objects);pred,_=terminal.apply(snapshot,*arrays,pred,review,normal)
            assert pred.get('status')=='active';row['arms'][arm]=pred
            if arm=='baseline':core_snapshot=snapshot
            if arm=='combined':row['arms']['with_local_core']=review_lost_keep(core_snapshot,*arrays,row['arms']['baseline'],pred)
        if case.get('historical'):
            old=case['historical'];new=row['arms']['baseline'];assert new['filter_recommendation']==old['filter_recommendation'],case['key']
            for side in ['reference','target']:
                assert new['paired_evidence'][side]['input_sha256']==old['paired_evidence'][side]['input_sha256'],(case['key'],side)
                assert abs(new['paired_evidence'][side]['screw_margin']-old['paired_evidence'][side]['screw_margin'])<1e-5
        results.append(row);save(out/'results.json',results)
        print(case['key'],{k:v['filter_recommendation'] for k,v in row['arms'].items()},flush=True)
    summary={}
    requested={'OK-000001','OK-000008','OK-000009','OK-000015'}
    for arm in ['combined','with_local_core']:
        lost=[r['key'] for r in results if r['expected']=='keep' and r['arms']['baseline']['filter_recommendation']=='keep' and r['arms'][arm]['filter_recommendation']!='keep']
        remaining=[r['key'] for r in results if r['key'] in requested and r['arms'][arm]['filter_recommendation']=='keep']
        baseline_missing=[r['key'] for r in results if r['expected']=='keep' and r['arms']['baseline']['filter_recommendation']!='keep']
        summary[arm]=dict(lost_protected=lost,remaining_requested_OK=remaining,baseline_missing_historical=baseline_missing,screen_passed=not lost and not remaining and not baseline_missing)
    save(out/'summary.json',dict(arms=summary,candidate_count=len(results),activation_allowed=False,production_changed=False))
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
