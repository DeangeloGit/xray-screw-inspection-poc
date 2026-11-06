"""Full isolated detector rerun with additional exposed-part proposals."""
import os,sys,copy,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));EXP=ROOT/'workspace/dino-4r-visible-screw-20261106/v2';OUT=EXP/'final';BASE=ROOT/'workspace/dino-4r-blackblock-20261106/final'
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1'
import numpy as np,cv2,detector,overkill_pilot
import visible_screw_policy as policy
import improvement_policy
from model_manager import ModelManager
from answered_batch_report import read,save,sha
def main():
    cv2.setNumThreads(4);plan=read(EXP/'reviewed-plan.json');plan.update(policy=policy.VERSION,experiment_hashes={str(Path(p).resolve()):sha(p) for p in (Path(__file__),policy.__file__,policy.geometry.__file__,policy.base.__file__,improvement_policy.__file__,EXP.parent/'visible-part-bank.npz',EXP/'experiment-plan.json',EXP/'answers-B-reviewed.json')})
    save(OUT/'plan.json',plan);shutil.copy2(EXP/'answers-B-reviewed.json',OUT/'answers.json');shutil.copy2(BASE/'provenance.json',OUT/'provenance.json')
    save(OUT/'report-meta.json',dict(title='4r 可見螺絲B部位｜全圖資結果',expected_answers=101,reviewed_scoring=True,methods=dict(r3='原r3（B部位答案）',recovery='原保留基準（B部位答案）',pilot='B局部辨識試驗'),protect_previous_answer_hits=True,protect_r3_candidates=False,protect_unmatched=True,policy_description='基礎47＋65雙圖不變。新增可見部位候選，局部補救使用50＋77範例；黑塊本體不輸入局部分類器。',comparison_description='本輪真正重跑全批。三版本皆以相同B部位答案評分，原59處保護。候選不讀答案；128由使用者確認B，其餘9張B定位由助理審核。第136張參與幾何診斷，整批為開發回歸，非獨立驗收。',answer_intro='<p>依使用者確認，把答案10定位到黑塊右側露出的螺絲B。128為使用者確認部位，精確框及其餘9張由助理影像審核；另存校正版，原始答案不改。其餘答案沿用，共101處。所有比較版本使用同一套B答案，黑塊框不再冒充B命中。</p>'))
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error and snap.identity==plan['model']['fingerprint'];policy.configure(np.load(EXP.parent/'visible-part-bank.npz')['bank'],read(EXP/'experiment-plan.json'))
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
        assert similarity_recoveries is not None;similarity_recoveries.extend(extras);state['objects']=policy.Objects(qr,qt,cs+oldadd+extras);return cs,res
    detector.proposals=proposals;detector.classify_dino_candidate=lambda snap,tar,ref,c:policy.classify(snap,ref,tar,c,state['objects']);overkill_pilot.apply=lambda snap,ref,tar,c,p:p
    for row in plan['items']:
        key=row['key']
        for dest,source in [('r3','r3'),('recovery','pilot')]:
            folder=OUT/'runs'/dest/key;folder.mkdir(parents=True,exist_ok=True)
            for file in ('result.json','complete.json'):shutil.copy2(BASE/'runs'/source/key/file,folder/file)
        folder=OUT/'runs/pilot'/key
        if (folder/'complete.json').exists():continue
        start=time.perf_counter();r=detector.detect(Path(plan['source'])/'Golden.tiff',row['path'],key,.13,model_snapshot=snap,output_directory=folder);old=read(BASE/'runs/pilot'/key/'result.json');cs=r['candidates']+r['filtered_candidates'];idx={policy.box(c):c for c in cs}
        for c in old['candidates']+old['filtered_candidates']:
            new=idx[policy.box(c)];assert new['id']==c['id'];assert new['classification']==c['classification'],(key,c['id'])
        save(folder/'complete.json',dict(key=key,policy=policy.VERSION,result_sha256=sha(folder/'result.json'),kept=r['proposal_count'],excluded=r['filtered_count'],old_candidates_exactly_preserved=True));print('FULL',key,'total',len(cs),'kept',r['proposal_count'],'seconds',round(time.perf_counter()-start,1),flush=True)
    for group in ('hashes','experiment_hashes'):
        assert all(sha(p)==h for p,h in plan[group].items())
    save(OUT/'run-complete.json',dict(complete=True,fresh_full_detection=True,all_old_candidate_classifications_exactly_preserved=True,production_unchanged=True))
if __name__=='__main__':main()
