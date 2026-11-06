"""Isolated full inference with image-derived canonical crops; production unchanged."""
import argparse,copy,json,os,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1';sys.path.insert(0,str(ROOT))
    import cv2,numpy as np,detector,overkill_pilot
    import correspondence_policy as policy
    import stability_policy,correspondence_geometry
    import improvement_policy
    from model_manager import ModelManager
    from answered_batch_run import save,sha
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    plan=read(base/'plan.json');plan.update(baseline_directory=str(base),policy=policy.VERSION)
    plan['experiment_hashes']={str(Path(f).resolve()):sha(f) for f in (policy.__file__,stability_policy.__file__,correspondence_geometry.__file__,improvement_policy.__file__,__file__)}
    if (out/'plan.json').exists():assert read(out/'plan.json')==plan
    else:save(out/'plan.json',plan)
    for name in ('answers.json','provenance.json'):shutil.copy2(base/name,out/name)
    save(out/'report-meta.json',dict(title='4r 參照配對與完整輪廓｜全圖資結果｜2026-11-06',methods=dict(r3='原 r3',recovery='前輪穩定性版',pilot='本輪參照配對版'),policy_description='先定位同一物件，再做參照位移配對、低對比背景複核及完整輪廓重看；47＋65 雙圖規則不變。',comparison_description='全批重新偵測與推論；答案只用於事後驗證。候選框與實際取圖框分開記錄，答案依各版本實際取圖框核對。這是同批開發回歸，沒有獨立新影像。',protect_previous_answer_hits=True,protect_r3_candidates=False,protect_unmatched=True))
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error and snap.identity==plan['model']['fingerprint']
    original=detector.proposals;state={}
    def proposals(ref,target,mask,threshold,structure_changes=None,similarity_recoveries=None):
        cs,res=original(ref,target,mask,threshold,structure_changes,similarity_recoveries)
        cs+=improvement_policy.supplemental(ref,target,mask,detector.compensate_brightness(ref,target),cs+list(similarity_recoveries or []))
        additions=[]
        for c in sorted(similarity_recoveries or [],key=lambda c:-c['score']):
            if not overkill_pilot.overlapping(c,cs):
                checked,explained=detector.check_candidate(ref,target,copy.deepcopy(c),threshold)
                if not explained:additions.append(checked)
        q=[(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in (ref,target)]
        state['objects']=policy.Objects(*q,cs+additions)
        return cs,res
    detector.proposals=proposals
    detector.classify_dino_candidate=lambda snapshot,target,ref,c:policy.classify(snapshot,ref,target,c,state['objects'])
    overkill_pilot.apply=lambda snapshot,ref,target,c,pred:pred
    for row in plan['items']:
        key=row['key']
        for dest_method,src_method in [('r3','r3'),('recovery','pilot')]:
            dest=out/'runs'/dest_method/key;dest.mkdir(parents=True,exist_ok=True)
            for name in ('result.json','complete.json'):shutil.copy2(base/'runs'/src_method/key/name,dest/name)
        folder=out/'runs/pilot'/key
        if (folder/'complete.json').exists():continue
        t=time.perf_counter();r=detector.detect(Path(plan['source'])/'Golden.tiff',row['path'],key,.13,model_snapshot=snap,output_directory=folder)
        cs=r['candidates']+r['filtered_candidates'];old=read(base/'runs/pilot'/key/'result.json')
        assert {policy.box(c) for c in cs}=={policy.box(c) for c in old['candidates']+old['filtered_candidates']}
        assert all(c['classification']['canonical_object']['fresh_inference'] for c in cs)
        save(folder/'complete.json',dict(key=key,method='pilot',policy=policy.VERSION,kept=r['proposal_count'],excluded=r['filtered_count'],seconds=round(time.perf_counter()-t,2),result_sha256=sha(folder/'result.json')))
        print('STABILITY',key,'keep',r['proposal_count'],'exclude',r['filtered_count'],round(time.perf_counter()-t,2),flush=True)
    assert all(sha(p)==h for p,h in plan['hashes'].items())
    assert all(sha(p)==h for p,h in plan['experiment_hashes'].items())
    save(out/'run-complete.json',dict(complete=True,protected_files_unchanged=True,experiment_frozen=True,photos=len(plan['items']),methods=plan['methods']))

if __name__=='__main__':main()
