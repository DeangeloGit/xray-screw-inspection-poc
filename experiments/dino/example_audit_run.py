"""Fresh full detector run, retaining every 69-hit-baseline alarm."""
import os,sys,copy,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));EXP=ROOT/'workspace/dino-4r-example-audit-20261106';OUT=EXP/'final';BASE=ROOT/'workspace/dino-4r-visible-screw-20261106/v3/final';BEXP=BASE.parent
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1'
import numpy as np,cv2,detector,overkill_pilot
import example_audit_policy as policy
import improvement_policy
from model_manager import ModelManager
from answered_batch_report import read,save,sha
def main():
    OUT.mkdir(exist_ok=True);cv2.setNumThreads(4);plan=read(BASE/'plan.json');plan.update(policy=policy.VERSION)
    plan['experiment_hashes'].update({str(Path(p).resolve()):sha(p) for p in (Path(__file__),policy.__file__,EXP/'letterbox-112-bank.npz')})
    save(OUT/'plan.json',plan)
    for name in ('answers.json','provenance.json','manual-feedback.json'):shutil.copy2(BASE/name,OUT/name)
    save(OUT/'report-meta.json',dict(title='4r 範例與完整取圖複核｜全圖資結果',expected_answers=101,reviewed_scoring=True,methods=dict(r3='原r3（相同答案）',recovery='前輪69處基準',pilot='完整比例與四範圍複核'),protect_previous_answer_hits=True,protect_r3_candidates=False,protect_unmatched=True,policy_description='原47＋65雙圖及B局部分支維持。完整輪廓補救用相同47＋65來源另建保留比例的範例庫，參照／待測做四範圍新推論；沒有加入目標黑塊正例。',comparison_description='本輪全批重新檢測；所有版本使用相同101處答案，答案及比對規則未更改。原69處須全保住，每張照片框外警報不增加。此批參與開發，非獨立驗收。',answer_intro='<p>沿用前輪101處答案與B部位修正，這輪沒有移動或新增答案。128的B部位由使用者確認，精確框與其餘9張B定位為助理審核；權限來源沿用前輪紀錄。</p>'))
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error and snap.identity==plan['model']['fingerprint'];policy.configure(np.load(BEXP.parent/'visible-part-bank.npz')['bank'],read(BEXP/'experiment-plan.json'),np.load(EXP/'letterbox-112-bank.npz')['bank'])
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
        start=time.perf_counter();r=detector.detect(Path(plan['source'])/'Golden.tiff',row['path'],key,.13,model_snapshot=snap,output_directory=folder);old=read(BASE/'runs/pilot'/key/'result.json');cs=r['candidates']+r['filtered_candidates'];idx={policy.box(c):c for c in cs};changed=[]
        assert len(cs)==len(old['candidates'])+len(old['filtered_candidates'])
        for c in old['candidates']+old['filtered_candidates']:
            new=idx[policy.box(c)];assert new['id']==c['id']
            if new['classification']!=c['classification']:
                assert c['classification']['filter_recommendation']=='exclude' and new['classification']['filter_recommendation']=='keep' and 'example_crop_review' in new['classification'],(key,c['id']);changed.append(c['id'])
        save(folder/'complete.json',dict(key=key,policy=policy.VERSION,result_sha256=sha(folder/'result.json'),kept=r['proposal_count'],excluded=r['filtered_count'],original_keeps_exactly_preserved=True,changed_candidates=changed));print('FULL',key,'total',len(cs),'kept',r['proposal_count'],'changed',changed,'seconds',round(time.perf_counter()-start,1),flush=True)
    for group in ('hashes','experiment_hashes'):assert all(sha(p)==h for p,h in plan[group].items())
    assert sha(BASE/'answers.json')==sha(OUT/'answers.json')
    save(OUT/'run-complete.json',dict(complete=True,fresh_full_detection=True,original_keep_classifications_exactly_preserved=True,production_unchanged=True,answers_unchanged=True))
if __name__=='__main__':main()
