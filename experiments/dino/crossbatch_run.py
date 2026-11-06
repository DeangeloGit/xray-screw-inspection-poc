"""Frozen 4r validation of the user-selected MPT10 corpus; no tuning on results."""
import os,sys,copy,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-crossbatch-20261106';PRIOR=ROOT/'workspace/dino-4r-example-audit-20261106/final';BEXP=ROOT/'workspace/dino-4r-visible-screw-20261106/v3'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1'
import numpy as np,cv2,detector,overkill_pilot
import example_audit_policy as policy
import improvement_policy
from model_manager import ModelManager
from answered_batch_report import read,save,sha
def main():
    cv2.setNumThreads(4);prior=read(PRIOR/'plan.json');inventory=read(OUT/'source-inventory.json');gold=Path(prior['source'])/'Golden.tiff';gh=sha(gold);items=[]
    for row in inventory:
        p=Path(row['path']);serial=p.stem.rsplit('_',1)[-1];key=row['label'].lower()+'-'+serial.zfill(3);items.append(dict(row,key=key,name=p.name,machine='MPT10',is_reference=row['sha256']==gh,reference=str(gold)))
    assert len(items)==100 and sum(r['is_reference'] for r in items)==1
    frozen=dict(prior['hashes'],**prior['experiment_hashes']);frozen[str(Path(__file__).resolve())]=sha(Path(__file__));frozen[str(OUT/'source-inventory.json')]=sha(OUT/'source-inventory.json')
    for row in items:frozen[row['path']]=row['sha256']
    plan=dict(source=str(Path(items[0]['path']).parents[1]),reference=str(gold),items=items,model=prior['model'],hashes=frozen,policy=policy.VERSION,threshold=.13,independent_new_defect_images=0,other_good_images=89,reference_self_images=1,annotation_source=str(PRIOR/'answers.json'),scope='10 NG are identical bytes/oriented pixels to development set; 89 other OK plus one identical Golden reference; OK labels inherited from supplied folder, not fresh manual annotations.')
    if (OUT/'plan.json').exists():assert read(OUT/'plan.json')==plan,'Frozen plan changed; use a new output directory'
    else:save(OUT/'plan.json',plan)
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error and snap.identity==plan['model']['fingerprint'];policy.configure(np.load(BEXP.parent/'visible-part-bank.npz')['bank'],read(BEXP/'experiment-plan.json'),np.load(PRIOR.parent/'letterbox-112-bank.npz')['bank'])
    original=detector.proposals;check=detector.check_candidate;overlap=overkill_pilot.overlapping;state={}
    detector.check_candidate=lambda ref,tar,c,t:(c,False) if c.get('recovery')=='r4_visible_part' else check(ref,tar,c,t)
    overkill_pilot.overlapping=lambda c,previous:any(policy.box(c)==policy.box(p) for p in previous) if c.get('recovery')=='r4_visible_part' else overlap(c,previous)
    def proposals(ref,target,mask,threshold,structure_changes=None,similarity_recoveries=None):
        cs,res=original(ref,target,mask,threshold,structure_changes,similarity_recoveries);cs+=improvement_policy.supplemental(ref,target,mask,detector.compensate_brightness(ref,target),cs+list(similarity_recoveries or []));oldadd=[]
        for c in sorted(similarity_recoveries or [],key=lambda c:-c['score']):
            if not overlap(c,cs):
                checked,explained=check(ref,target,copy.deepcopy(c),threshold)
                if not explained:oldadd.append(checked)
        qr,qt=[(np.clip(a,0,1)*255).astype('uint8').astype('float32')/255 for a in (ref,target)];extras=[]
        for p in policy.geometry.proposals(qr,qt):
            p={k:v for k,v in p.items() if k!='mask'};x,y,w,h=p['box']
            if any(policy.box(c)==tuple(p['box']) for c in cs+oldadd):continue
            extras.append(dict(x=x,y=y,w=w,h=h,area=p['area'],score=-1.,normal_support=0.,aspect=max(w,h)/min(w,h),fill=p['area']/(w*h),bipolar=0.,contrast=p['mean_difference'],shape_similarity=0.,recovery='r4_visible_part',change_type='visible_screw_candidate',visible_part=p))
        assert similarity_recoveries is not None;similarity_recoveries.extend(extras);state.update(objects=policy.Objects(qr,qt,cs+oldadd+extras),baseline_kept=[],baseline={});return cs,res
    def classify(snap,tar,ref,c):
        objects=state['objects'];pred=policy.classify(snap,ref,tar,c,objects);baseline=pred.get('example_crop_review',{}).get('previous',pred)
        if c.get('recovery')=='r4_visible_part':
            # New accepted contours can affect duplicate suppression. Independently
            # recompute B verdicts using only the predecessor's accepted contours.
            if objects.old_kept!=state['baseline_kept']:
                actual=objects.old_kept;objects.old_kept=state['baseline_kept']
                try:baseline=policy.base.classify(snap,ref,tar,c,objects)
                finally:objects.old_kept=actual
        elif baseline['filter_recommendation']=='keep':state['baseline_kept'].append(baseline['canonical_object']['box'])
        state['baseline'][str(c['id'])]=copy.deepcopy(baseline);return pred
    detector.proposals=proposals;detector.classify_dino_candidate=classify;overkill_pilot.apply=lambda snap,ref,tar,c,p:p
    for i,row in enumerate(sorted(items,key=lambda z:(z['label']!='NG',z['key'])),1):
        folder=OUT/'runs'/row['key']
        if (folder/'complete.json').exists():
            done=read(folder/'complete.json');assert sha(folder/'result.json')==done['result_sha256'];continue
        start=time.perf_counter();r=detector.detect(gold,row['path'],row['key'],.13,model_snapshot=snap,output_directory=folder)
        save(folder/'baseline69-classifications.json',state['baseline']);cs=r['candidates']+r['filtered_candidates'];assert len(state['baseline'])==len(cs)
        before=sum(v['filter_recommendation']=='keep' for v in state['baseline'].values());changed=[c['id'] for c in cs if c['classification']['filter_recommendation']!=state['baseline'][str(c['id'])]['filter_recommendation']]
        save(folder/'complete.json',dict(key=row['key'],result_sha256=sha(folder/'result.json'),baseline_sha256=sha(folder/'baseline69-classifications.json'),kept=r['proposal_count'],excluded=r['filtered_count'],baseline_kept=before,changed_candidates=changed,seconds=round(time.perf_counter()-start,1)))
        print('FULL',i,'/',len(items),row['key'],'candidates',len(cs),'keep',r['proposal_count'],'baseline',before,'changed',changed,'sec',round(time.perf_counter()-start,1),flush=True)
    assert all(sha(p)==h for p,h in frozen.items())
    save(OUT/'run-complete.json',dict(complete=True,fresh_full_detection=True,frozen_policy_unchanged=True,source_and_production_hashes_unchanged=True,photos=100))
if __name__=='__main__':main()
