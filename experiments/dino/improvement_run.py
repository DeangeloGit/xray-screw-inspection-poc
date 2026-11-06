"""Run the fixed image-only 4r policy in process-local hooks, never production."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1';sys.path.insert(0,str(ROOT))
    import cv2,detector,overkill_pilot
    from model_manager import ModelManager
    import improvement_policy as policy
    from answered_batch_run import sha,save
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    plan=read(base/'plan.json');plan['baseline_directory']=str(base);plan['policy']=policy.VERSION;plan['rules']=policy.RULES
    plan['experiment_hashes']={str(Path(policy.__file__)):sha(policy.__file__),str(Path(__file__).resolve()):sha(__file__)}
    if (out/'plan.json').exists():assert read(out/'plan.json')==plan
    else:save(out/'plan.json',plan)
    for name in ('answers.json','provenance.json'):shutil.copy2(base/name,out/name)
    save(out/'report-meta.json',dict(title='4r 改善實驗｜全圖資結果｜2026-11-06',methods=dict(r3='原 r3',recovery='上輪過殺試驗版',pilot='本輪改善實驗'),policy_description='本輪只在隔離程序測試碎片合併、雙尺寸共識與結構複核。',comparison_description='比較原 r3、上輪 52/100 試驗版與本輪改善。門檻在同批影像上探索選定，屬開發回歸測試，沒有獨立新圖。正式程式與模型未修改。',protect_previous_answer_hits=True))
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested'])
    assert snap.identity==plan['model']['fingerprint'] and not snap.error
    original_proposals=detector.proposals;original_apply=overkill_pilot.apply
    def proposals(ref,target,mask,threshold,structure_changes=None,similarity_recoveries=None):
        cs,res=original_proposals(ref,target,mask,threshold,structure_changes,similarity_recoveries)
        prior=cs+list(similarity_recoveries or [])
        extras=policy.supplemental(ref,target,mask,detector.compensate_brightness(ref,target),prior)
        return cs+extras,res
    detector.proposals=proposals
    overkill_pilot.apply=lambda snap,ref,target,c,pred:policy.improve(snap,ref,target,c,pred,original_apply)
    for row in plan['items']:
        key=row['key']
        for dest_method,src_method in [('r3','r3'),('recovery','pilot')]:
            dest=out/'runs'/dest_method/key;dest.mkdir(parents=True,exist_ok=True)
            for name in ('result.json','complete.json'):shutil.copy2(base/'runs'/src_method/key/name,dest/name)
        folder=out/'runs'/'pilot'/key
        if (folder/'complete.json').exists():continue
        t=time.perf_counter();r=detector.detect(Path(plan['source'])/'Golden.tiff',row['path'],key,.13,model_snapshot=snap,output_directory=folder)
        old=read(base/'runs'/'pilot'/key/'result.json');geom=lambda c:tuple(c[k] for k in ('x','y','w','h'))
        actual={geom(c):c for c in r['candidates']+r['filtered_candidates']}
        assert all(geom(c) in actual for c in old['candidates']+old['filtered_candidates'])
        r3=read(base/'runs'/'r3'/key/'result.json')
        assert all(actual[geom(c)]['classification']['filter_recommendation']=='keep' for c in r3['candidates'])
        assert all(c['classification']['status']=='active' for c in actual.values())
        save(folder/'complete.json',dict(key=key,method='pilot',policy=policy.VERSION,kept=r['proposal_count'],excluded=r['filtered_count'],seconds=round(time.perf_counter()-t,2),result_sha256=sha(folder/'result.json')))
        print('IMPROVED',key,'keep',r['proposal_count'],'exclude',r['filtered_count'],round(time.perf_counter()-t,2),flush=True)
    assert all(sha(p)==h for p,h in plan['hashes'].items())
    assert all(sha(p)==h for p,h in plan['experiment_hashes'].items())
    save(out/'run-complete.json',dict(complete=True,protected_files_unchanged=True,experiment_frozen=True,photos=len(plan['items']),methods=plan['methods']))


if __name__=='__main__':main()
