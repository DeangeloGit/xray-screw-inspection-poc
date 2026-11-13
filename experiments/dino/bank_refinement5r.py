"""Isolated, source-disjoint 5r normal-example trial. Never activates a bank.

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
    ap.add_argument('--training-plan',type=Path,required=True)
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
    batch=ROOT/'workspace/5r-live/folder-batches/9c1f689b04d64536a0de3582270ca1ae'
    job=read(batch/'job.json');byid={r['id']:r for r in job['rows']}
    recipes=read(a.training_plan)
    training_ids=sorted({r['source'] for r in recipes})
    validation_ids=[r['id'] for r in job['rows'] if r['id'] not in training_ids]
    assert not set(training_ids)&set(validation_ids)
    assert not set(training_ids)&{'000001','000008','000009','000015'}
    train_serials={byid[i]['file'].split('_')[0] for i in training_ids}
    assert all(byid[i]['file'].split('_')[0] not in train_serials for i in validation_ids)
    plan=dict(schema_version=1,runner_sha256=sha(__file__),training_plan_sha256=sha(a.training_plan),formal_model=original.info(),model_manifest_sha256=sha(lean/'models'/original.requested/'manifest.json'),
        active_bank_sha256=sha(vr/'bank.npz'),part_bank_sha256=sha(partroot/'visible-part-bank.npz'),
        main_positive_count=n,main_normal_count=len(ids)-n,part_positive_count=50,part_normal_count=77,
        training_photos=[byid[i] for i in training_ids],validation_photos=[byid[i] for i in validation_ids],
        recipes=recipes,positive_policy='All existing verified positives kept byte-for-byte, including B128/B131/B132; no duplicate positive votes',
        negative_authority='User labels whole photos OK; selected crops visually checked by assistant as wires, not screw heads. This is not a new human candidate annotation.',
        split_scope='Disjoint source filenames, SHA and serials. Four known challenge errors influenced crop-family selection: not blind validation.',
        criteria=dict(no_lost_protected_screws=True,no_lost_existing_NG_alarm=True,no_training_photo_in_validation=True,
                      full_corpus_required_before_activation=True),production_changed=False)
    trainhashes=[]
    for i in training_ids:
        row=byid[i];source=Path(job['folder'])/row['file'];assert sha(source)==row['source_sha256']
        trainhashes.append(row['source_sha256'])
    assert not set(trainhashes)&{byid[i]['source_sha256'] for i in validation_ids}
    save(out/'plan.json',plan)
    main_extra=[];main_positive=[];part_extra=[];inventory=[]
    for index,row in enumerate(recipes):
        with Image.open(batch/'runs'/row['source']/'aligned.png') as f:arr=np.asarray(f.convert('L'),np.float32)/255
        x,y,w,h=row['box'];pad=row['pad']
        crop=part_image(arr,(x,y,w,h)) if row['kind'].startswith('visible') else arr[y-pad:y+h+pad,x-pad:x+w+pad]
        label=row.get('label','normal')
        im=dino.adjusted_image(original.manifest,crop);dest=out/'examples'/f'{label}-{index:02}.png';dest.parent.mkdir(exist_ok=True);im.save(dest)
        vector=dino.example_features(original.manifest,original.session,crop)
        if row['kind'].startswith('visible'):
            assert label=='normal';part_extra.append(vector)
        elif label=='screw':main_positive.append(vector)
        else:main_extra.append(vector)
        inventory.append(dict(row,label=label,id=f'{label}-local-{index:02}',image=str(dest.relative_to(out)),sha256=sha(dest),feature_sha256=hashlib.sha256(vector.tobytes()).hexdigest()))
    positive_array=np.asarray(main_positive) if main_positive else np.empty((0,*bank.shape[1:]),dtype=bank.dtype)
    main_trial=np.concatenate([bank[:n],positive_array,bank[n:],np.asarray(main_extra)]);part_trial=np.concatenate([part,np.asarray(part_extra)])
    trial_n=n+len(main_positive)
    trial_ids=ids[:n]+[r['id'] for r in inventory if r['label']=='screw']+ids[n:]+[r['id'] for r in inventory if r['label']=='normal' and not r['kind'].startswith('visible')]
    assert np.array_equal(main_trial[:n],bank[:n]) and np.array_equal(main_trial[trial_n:trial_n+len(bank)-n],bank[n:]) and np.array_equal(part_trial[:len(part)],part)
    np.savez_compressed(out/'main-trial.npz',bank=main_trial,n=trial_n,ids=np.array(trial_ids))
    np.savez_compressed(out/'part-trial.npz',bank=part_trial,n=50)
    save(out/'examples/manifest.json',inventory)
    cases=[]
    for rid in ['000001','000008','000009','000013','000015']:
        folder=batch/'runs'/rid;r=read(folder/'result.json')
        cases.append(dict(key='OK-'+rid,folder=str(folder),id=r['candidates'][0]['id'],label='known_OK_challenge',expected='exclude',historical=r['candidates'][0]['classification']))
    ng=ROOT/'workspace/5r-live/folder-batches/f2661437e1ce4ef19c5f10f107d35ab6/runs/000004'
    c=read(ng/'result.json')['candidates'][0]
    cases.append(dict(key='NG-existing',folder=str(ng),id=c['id'],label='NG_location_unconfirmed_protect_existing',expected='keep',historical=c['classification']))
    for photo,cid in [('128',10),('135',88)]:
        cases.append(dict(key='human-'+photo,folder=str(arc/'dino-4r-crossbatch-20261106/runs'/('ng-'+photo)),id=cid,label='human_confirmed_screw',expected='keep'))
    for photo in map(str,range(128,138)):
        folder=ROOT/'workspace/dino-4r-crossbatch-20261106/runs'/('ng-'+photo)
        for c in read(folder/'result.json')['candidates']:
            if c.get('recovery')=='r4_visible_part':
                cases.append(dict(key='B-'+photo,folder=str(folder),id=c['id'],label='historical_answer_B_control',expected='keep'))
    save(out/'screen-cases.json',cases)
    session=TensorCache(original.session,original.identity,limit=1500)
    results=[]
    for case in cases:
        folder=Path(case['folder']);r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id'])
        candidate=next(c for c in cs if c['id']==case['id'])
        arrays=[]
        for name in ['reference','aligned']:
            with Image.open(folder/(name+'.png')) as im:arrays.append(np.asarray(im.convert('L'),np.float32)/255)
        session.clear();row=dict(key=case['key'],label=case['label'],expected=case['expected'],arms={},source_result_sha256=sha(folder/'result.json'))
        for arm,main_bank,part_bank in [('baseline',bank,part),('main_only',main_trial,part),('part_only',bank,part_trial),('combined',main_trial,part_trial)]:
            manifest=copy.deepcopy(original.manifest)
            selected_ids,selected_n=(trial_ids,trial_n) if len(main_bank)>len(bank) else (ids,n)
            manifest['example_bank']['screw']['ids']=selected_ids[:selected_n]
            manifest['example_bank']['normal']['ids']=selected_ids[selected_n:]
            snapshot=replace(original,manifest=manifest,feature_bank=main_bank,session=session)
            policy.configure(part_bank,config,review)
            objects=policy.Objects(*arrays,cs)
            pred=integrated.classify(snapshot,*arrays,candidate,objects)
            pred,_=terminal.apply(snapshot,*arrays,pred,review,normal)
            assert pred.get('status')=='active'
            row['arms'][arm]=pred
        if case.get('historical'):
            old=case['historical'];new=row['arms']['baseline']
            assert new['filter_recommendation']==old['filter_recommendation'],case['key']
            for side in ['reference','target']:
                assert new['paired_evidence'][side]['input_sha256']==old['paired_evidence'][side]['input_sha256'],(case['key'],side)
                assert abs(new['paired_evidence'][side]['screw_margin']-old['paired_evidence'][side]['screw_margin'])<1e-5
        results.append(row);save(out/'screen-results.json',results)
        print(case['key'],{k:v['filter_recommendation'] for k,v in row['arms'].items()},flush=True)
    summary={}
    for arm in ['main_only','part_only','combined']:
        lost=[r['key'] for r in results if r['expected']=='keep' and r['arms'][arm]['filter_recommendation']!='keep']
        remaining=[r['key'] for r in results if r['expected']=='exclude' and r['arms'][arm]['filter_recommendation']=='keep']
        summary[arm]=dict(lost_protected=lost,remaining_known_OK=remaining,screen_passed=not lost and not remaining)
    save(out/'screen-summary.json',dict(status='screened',arms=summary,baseline_exact_current_batch_reproduced=True,
         inference_scope='Selected candidates with complete proposal support, not sequential full-photo/full-corpus replay; must pass before full regression',
         training_sources_excluded_from_challenges=True,production_changed=False,activation_allowed=False))
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
