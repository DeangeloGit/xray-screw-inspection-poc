"""Re-execute the frozen 4r classifier with integrated MAIN reference banks."""
from integrated_bank_probe import ROOT,OUT,AUDIT,PRIOR,CURRENT,read,save
import argparse,copy,hashlib,time
from dataclasses import replace
from collections import OrderedDict
import numpy as np,cv2
from PIL import Image
from model_manager import ModelManager
import dino_paired_optimized as dino
import example_audit_policy as policy
import visible_screw_policy_v3 as visible
import connector_policy as terminal
import integrated_bank_policy as integrated
import answered_batch_report as common

class CachedSession:
    def __init__(self,session):self.session=session;self.cache=OrderedDict();self.fresh=0;self.hits=0
    def __getattr__(self,k):return getattr(self.session,k)
    def run(self,outputs,inputs):
        key=hashlib.sha256(next(iter(inputs.values())).tobytes()).hexdigest()
        if key in self.cache:self.hits+=1;self.cache.move_to_end(key);return self.cache[key]
        v=self.session.run(outputs,inputs);self.fresh+=1;self.cache[key]=v
        if len(self.cache)>1800:self.cache.popitem(last=False)
        return v

RAW_FEATURES=dino.features
class FeatureCache:
    def __init__(self,photo):
        self.values={};self.hits=0;self.fresh=0
        for p in (AUDIT/'all-features'/f'{photo.removeprefix("ng-")}.npz',OUT/'features'/f'{photo}.npz'):
            if p.exists():
                with np.load(p) as f:self.values.update({k:f[k] for k in f.files})
    def features(self,m,s,im):
        key=hashlib.sha256(im.tobytes()).hexdigest()
        if key in self.values:self.hits+=1;return self.values[key]
        v=RAW_FEATURES(m,s,im);self.values[key]=v;self.fresh+=1;return v
    def save(self,photo):
        p=OUT/'features'/f'{photo}.npz';p.parent.mkdir(exist_ok=True);np.savez_compressed(p,**self.values)

def configure():
    b=ROOT/'workspace/dino-4r-visible-screw-20261106';review=np.load(AUDIT/'letterbox-112-bank.npz')['bank'];policy.configure(np.load(b/'visible-part-bank.npz')['bank'],read(b/'v3/experiment-plan.json'),review)
    n=np.load(CURRENT/'normal-connector-bank.npz');return review,dict(bank=n['bank'],aspect=float(n['aspect']))
def snapshot(snap,arm,session=None):
    b=np.load(OUT/f'{arm}-bank.npz');m=copy.deepcopy(snap.manifest);n=int(b['n']);ids=b['ids'].tolist();m['example_bank']['screw']['ids']=ids[:n];m['example_bank']['normal']['ids']=ids[n:]
    if arm!='original':m['model_id']=f'DINO 4r 整合參考實驗：{n}螺絲＋{len(ids)-n}正常（{arm}）'
    return replace(snap,manifest=m,feature_bank=b['bank'],session=session or snap.session)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--photos');ap.add_argument('--arms',default='original,clean3_integrated');ap.add_argument('--provider',default='gpu');ap.add_argument('--stop-on-regression',action='store_true');a=ap.parse_args();cv2.setNumThreads(4)
    original=ModelManager(ROOT/'models',allow_cpu=True,execution_override=a.provider).snapshot('dino-paired-optimized-47-20261104-r3');assert not original.error
    review,normal=configure();plan=read(PRIOR/'plan.json');answers=read(PRIOR/'answers.json');baseline_rows={r['key']:r for r in read(CURRENT/'rows.json')};all_current={c['key']:c for c in read(CURRENT/'cases.json')};arms=a.arms.split(',')
    items=plan['items'] if not a.photos else [next(r for r in plan['items'] if r['key']==key) for key in a.photos.split(',')]
    for item in items:
        key=item['key'];dest=OUT/'replay'/key;dest.mkdir(parents=True,exist_ok=True)
        if all((dest/f'{arm}.json').exists() for arm in arms):continue
        start=time.perf_counter();folder=PRIOR/'runs'/key;r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']);ref,tar=[np.asarray(Image.open(folder/f'{n}.png').convert('L'),np.float32)/255 for n in ('reference','aligned')];flow=np.zeros((*ref.shape,2),np.float32)
        for z in r['local_alignment']:
            x,y,X,Y=z['bbox'];flow[y:Y,x:X]=[z['dx'],z['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12);cache=CachedSession(original.session);fc=FeatureCache(key)
        for module in (dino,policy,visible,terminal):module.features=fc.features
        for arm in arms:
            if (dest/f'{arm}.json').exists():continue
            s=snapshot(original,arm,cache);obj=policy.Objects(ref,tar,cs);preds={};matched={};changes=[];mismatch=[];upstream=[]
            for i,c in enumerate(cs):
                classifier=integrated if arm.endswith('_review') else policy
                p=classifier.classify(s,ref,tar,c,obj)
                if arm=='original':
                    old=c['classification']
                    if (p['filter_recommendation'],p['canonical_object']['box'])!=(old['filter_recommendation'],old['canonical_object']['box']):mismatch.append(c['id'])
                if key=='ng-128' and c['id'] in (22,40):upstream.append(dict(id=c['id'],verdict=p['filter_recommendation'],paired_evidence=p['paired_evidence']))
                p,check=terminal.apply(s,ref,tar,p,review,normal)
                preds[str(c['id'])]=p;cc=dict(c,classification=p);yes,edge=common.matches(common.native(cc,r,flow),answers.get(key,{}).get('marks',[]));matched[str(c['id'])]=yes
                current=all_current[f'{key}-{c["id"]}']
                if (p['filter_recommendation']=='keep')!=current['keep']:changes.append(c['id'])
                if i%30==0:print('PROGRESS',key,arm,i,len(cs),'fresh',cache.fresh,'feature cache',fc.hits,flush=True)
            hits=sorted({x for cid,p in preds.items() if p['filter_recommendation']=='keep' for x in matched[cid]});unmatched=sum(p['filter_recommendation']=='keep' and not matched[cid] for cid,p in preds.items());new=[int(cid) for cid,p in preds.items() if p['filter_recommendation']=='keep' and not all_current[f'{key}-{cid}']['keep']];newout=[cid for cid in new if not matched[str(cid)]];lost=sorted(set(baseline_rows[key]['hits'])-set(hits))
            result=dict(key=key,arm=arm,predictions=preds,answer_matches=matched,hits=hits,unmatched=unmatched,kept=sum(p['filter_recommendation']=='keep' for p in preds.values()),new_alerts=new,new_unmatched=newout,lost_original_answers=lost,changed_candidates=changes,baseline_mismatches=mismatch,upstream_pair_checks=upstream,terminal_rule_unchanged=True,answer_matching_recomputed=True,main_bank_sha256=hashlib.sha256((OUT/f'{arm}-bank.npz').read_bytes()).hexdigest());save(dest/f'{arm}.json',result)
            fc.save(key);print('REPLAY',key,arm,'hits',len(hits),'lost',lost,'outside',unmatched,'newout',newout,'changed',changes,'mismatch',mismatch,flush=True)
            assert not mismatch
            if arm=='original':assert not changes,('Current baseline reconstruction differs',key,changes)
            if a.stop_on_regression and arm!='original' and (lost or newout):
                save(OUT/f'stopped-{arm}.json',dict(photo=key,lost=lost,new_unmatched=newout,reason='Acceptance failed; do not expand a failed bank to the rest of the corpus.'));return
        save(dest/'timing.json',dict(seconds=round(time.perf_counter()-start,2),fresh_onnx=cache.fresh,exact_tensor_reuse=cache.hits,feature_cache_hits=fc.hits,feature_new=fc.fresh,provider=a.provider))
if __name__=='__main__':main()
