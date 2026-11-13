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
    ap.add_argument('--bundle',type=Path,required=True)
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
    import detector,overkill_pilot as pilot
    from new_model_run import four_r
    from live5r_review import ReviewBundle
    os.environ['XRAY_OVERKILL_PILOT']='1'
    bundle=ReviewBundle(a.bundle,allow_pending=True)
    manifest=copy.deepcopy(original.manifest);manifest['example_bank']['screw']['ids']=ids[:n];manifest['example_bank']['normal']['ids']=ids[n:]
    base=replace(original,manifest=manifest,feature_bank=bank);selected=bundle.tagged_snapshot(base)
    assert selected.identity!=base.identity
    assert np.array_equal(bundle.trial_snapshot(selected).feature_bank,np.load(ROOT/'workspace/5r-bank-trial-20261113/run3/main-trial.npz')['bank'])
    items=[]
    for bid,rids in [('9c1f689b04d64536a0de3582270ca1ae',['000001','000008','000009','000015']),('f2661437e1ce4ef19c5f10f107d35ab6',['000004'])]:
        batch=ROOT/'workspace/5r-live/folder-batches'/bid;job=read(batch/'job.json')
        for rid in rids:
            row=next(r for r in job['rows'] if r['id']==rid)
            items.append(dict(key=job['label']+'-'+rid,path=str(Path(job['folder'])/row['file']),reference=job['machine']['reference'],sha256=row['source_sha256'],reference_sha256=job['machine']['reference_sha256'],frozen=str(batch/'runs'/rid),expected_kept=0 if job['label']=='OK' else 1))
    oldplan=read(ROOT/'workspace/dino-4r-crossbatch-20261106/plan.json');item=next(r for r in oldplan['items'] if r['key']=='ng-135');items.append(dict(key='human-135',path=item['path'],reference=item['reference'],sha256=item['sha256'],reference_sha256=sha(item['reference']),frozen=str(ROOT/'workspace/dino-4r-crossbatch-20261106/runs/ng-135'),protected_candidate=88))
    for item in items:
        assert sha(item['path'])==item['sha256'];assert sha(item['reference'])==item['reference_sha256']
    save(out/'plan.json',dict(runner_sha256=sha(__file__),bundle_manifest_sha256=sha(a.bundle/'manifest.json'),items=items,provider='cpu',fresh_detector=True,production_changed=False))
    rows=[]
    for item in items:
        folder=out/'runs'/item['key'];folder.mkdir(parents=True)
        cache=TensorCache(original.session,original.identity,limit=1800);snap=replace(selected,session=cache)
        policy.configure(part,config,review)
        print('START FRESH',item['key'],flush=True)
        with four_r(detector,pilot,snap,review,normal):
            before=detector.detect(item['reference'],item['path'],item['key'],threshold=.13,model_snapshot=snap,output_directory=folder)
        baseline=copy.deepcopy(before);after=bundle.apply(snap,before,folder,review,normal);save(folder/'result.json',after)
        expected=read(Path(item['frozen'])/'result.json');assert after['pre_ai_count']==expected['pre_ai_count'],('proposal count changed',item['key'])
        assert sha(folder/'reference.png')==sha(Path(item['frozen'])/'reference.png'),('reference changed',item['key'])
        assert sha(folder/'aligned.png')==sha(Path(item['frozen'])/'aligned.png'),('alignment changed',item['key'])
        if 'expected_kept' in item:assert len(after['candidates'])==item['expected_kept'],item['key']
        if 'protected_candidate' in item:assert item['protected_candidate'] in {c['id'] for c in after['candidates']}
        old_excluded={c['id']:c for c in baseline['filtered_candidates']};new_excluded={c['id']:c for c in after['filtered_candidates']}
        assert all(new_excluded[k]==v for k,v in old_excluded.items())
        assert after['proposal_count']+after['filtered_count']==after['pre_ai_count']
        assert after['high_count']+after['review_count']==after['proposal_count']
        assert after['model']['fingerprint']==snap.identity
        assert np.array_equal(policy.base.BANK,part), 'Trial part bank leaked into next original pipeline'
        row=dict(key=item['key'],before=baseline['proposal_count'],after=after['proposal_count'],candidates=after['pre_ai_count'],alignment_and_reference_exact=True,prior_exclusions_identical=True,counts_consistent=True,model_fingerprint=snap.identity,banks=after['local_review5r'])
        rows.append(row);save(out/'rows.json',rows);print('FRESH PASSED',item['key'],row['before'],row['after'],flush=True)
    save(out/'summary.json',dict(status='passed',photos=len(rows),fresh_detector=True,model='active52+90 plus alarm postreview',pipeline_cache_identity_changed=True,production_changed=False,scope='Six selected fresh images, not a full161 fresh detector run'))

if __name__=='__main__':main()
