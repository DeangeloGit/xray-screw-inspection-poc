"""Train on fixed three photos, freeze, then score untouched seven-photo split."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-hardnegative-20261106';PREV=ROOT/'workspace/dino-4r-blackblock-20261106';OUT.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from blackblock_ablation import cut,score
from hardnegative_policy import difference,gate
from answered_batch_report import matches,sha
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    from model_manager import ModelManager
    from dino_paired_optimized import example_features
    import cv2
    cv2.setNumThreads(4)
    prior=read(PREV/'experiment-plan.json');cs=read(PREV/'final/cases.json');ci={c['key']:c for c in cs};pred=read(PREV/'ablation-results.json');pi={f'{z["photo"]}-{z["id"]}':z for z in pred}
    answers=read(PREV/'answers-corrected.json');train=prior['training_photos'];held=prior['heldout_photos']
    # Only Golden/reference patches, visually inspected in training context.
    negatives=['128-80','131-45','131-38','131-62','128-30','128-96','128-130']
    plan=dict(training_photos=train,heldout_photos=held,negative_examples=[dict(key=k,side='reference',label='normal',authority='Golden參照既有結構，開發照片裁圖經影像審核；非使用者逐點標註') for k in negatives],positive_examples=prior['added_examples'],threshold_grid=[0,.05,.1,.15,.2,.25,.3,.35,.4],difference=dict(reference_motion_radius=3,dark_cutoff=.45,added_darkness=.15,min_component_area=16,min_novel_share=.5,brightness='median outside object'),selection='training only: no new unmatched candidates, preserve all baseline; maximize added answer hits then lowest threshold; freeze before heldout',uncertain_case='128-3 and counterparts remain unmatched, never used as normal examples',protected_hashes=prior['protected_hashes'],independence=prior['independence'])
    save(OUT/'experiment-plan.json',plan)
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(prior['model']['requested']);assert not snap.error and snap.identity==prior['model']['fingerprint']
    positivebank=np.load(PREV/'experimental-bank.npz')['bank'];extra=[];(OUT/'negative-examples').mkdir(exist_ok=True)
    for k in negatives:
        z=pi[k];assert z['photo'] in train
        a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{z["photo"]}.npz');ref=(np.clip(a['ref'],0,1)*255).astype('uint8').astype('float32')/255
        crop=cut(ref,z['box'],'original',z['reference_offset']);Image.fromarray(np.uint8(crop*255)).save(OUT/'negative-examples'/f'{k}.png');extra.append(example_features(snap.manifest,snap.session,crop))
    hardbank=np.concatenate([positivebank,np.asarray(extra)]);np.savez_compressed(OUT/'experimental-bank.npz',bank=hardbank)
    assert np.array_equal(hardbank[:115],positivebank)
    base={c['key'] for c in cs if c['keep']['pilot']};truth={c['key']:matches(c['native'],answers.get(c['photo'],{}).get('marks',[]))[0] for c in cs}
    def metrics(kept,photos):
        subset=[ci[k] for k in kept if ci[k]['photo'] in photos];hits={(c['photo'],i) for c in subset for i in truth[c['key']]};bad=sorted(c['key'] for c in subset if not truth[c['key']])
        return dict(answer_hits=len(hits),hits=sorted(map(list,hits)),unmatched=len(bad),unmatched_candidates=bad,kept=len(subset),big_block_hits=sum((p,10) in hits for p in photos))
    def features_for(photos):
        rows=[]
        for p in photos:
            a=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays'/f'{p}.npz');qr,qt=[(np.clip(a[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')];cache=np.load(PREV/'features'/f'{p}.npz')
            for c in [c for c in cs if c['photo']==p]:
                z=pi[c['key']];old=z['variants']['original_new'];pairs={}
                for name,bank in [('positive',positivebank),('hardnegative',hardbank)]:
                    pairs[name]={side:dict(score(cache[old[side]['input_sha256']],bank,50),input_sha256=old[side]['input_sha256']) for side in ('reference','target')}
                rows.append(dict(key=c['key'],photo=p,eligible=c['paired_evidence']['target']['label']!='screw' and not c['rules'],baseline_keep=c['key'] in base,box=z['box'],reference_offset=z['reference_offset'],pairs=pairs,difference=difference(qr,qt,z['box'],z['reference_offset'])))
        return rows
    training=features_for(train);save(OUT/'training-scores.json',training);selected={};grid=[]
    for bankname in ('positive','hardnegative'):
        choices=[]
        for threshold in plan['threshold_grid']:
            conf=dict(target_min=threshold);added={z['key'] for z in training if z['eligible'] and gate(z['pairs'][bankname],z['difference'],conf)}-base;m=metrics(base|added,train);entry=dict(bank=bankname,config=conf,metrics=m,added=sorted(added),new_unmatched=sorted(set(m['unmatched_candidates'])-set(metrics(base,train)['unmatched_candidates'])));grid.append(entry)
            if not entry['new_unmatched']:choices.append(entry)
        selected[bankname]=max(choices,key=lambda e:(e['metrics']['answer_hits'],-e['config']['target_min'])) if choices else None
    save(OUT/'training-selection.json',dict(grid=grid,selected=selected));print('FROZEN TRAINING',[(k,v['config'] if v else None,v['added'] if v else None) for k,v in selected.items()],flush=True)
    freeze={str(p):sha(p) for p in (Path(__file__),ROOT/'experiments/dino/hardnegative_policy.py',OUT/'experiment-plan.json',OUT/'training-selection.json',OUT/'experimental-bank.npz')};save(OUT/'frozen-before-heldout.json',freeze)
    rows=training+features_for(held+['golden']);save(OUT/'all-scores.json',rows);variants={}
    for bankname in ('positive','hardnegative'):
        for usegate in (False,True):
            conf=(selected[bankname] or {}).get('config',dict(target_min=1));added=set()
            for z in rows:
                pair=z['pairs'][bankname];yes=gate(pair,z['difference'],conf) if usegate else pair['target']['margin']>=0 and pair['reference']['margin']<0
                if z['eligible'] and yes:added.add(z['key'])
            kept=base|added;m=metrics(kept,train+held);per={p:metrics(kept,[p]) for p in train+held};bad=set(m['unmatched_candidates'])-set(metrics(base,train+held)['unmatched_candidates'])
            variants[bankname+('_difference' if usegate else '_only')]=dict(config=conf if usegate else None,all=m,training=metrics(kept,train),heldout=metrics(kept,held),per_photo=per,added=sorted(kept-base),new_unmatched=sorted(bad),passes_safety=not bad and all(per[p]['unmatched']<=metrics(base,[p])['unmatched'] for p in per))
    save(OUT/'evaluation.json',dict(baseline=metrics(base,train+held),variants=variants))
    assert all(sha(p)==h for p,h in freeze.items());assert all(sha(p)==h for p,h in plan['protected_hashes'].items())
    for k,v in variants.items():print(k,'hits',v['all']['answer_hits'],'big',v['all']['big_block_hits'],'heldbig',v['heldout']['big_block_hits'],'outside',v['all']['unmatched'],'safe',v['passes_safety'],flush=True)
if __name__=='__main__':main()
