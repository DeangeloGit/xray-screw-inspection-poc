"""Replay the unchanged 79 policy with alternative MAIN example banks.

Frozen image alignment and candidate set; no connector veto and no new rule.
Baseline reconstruction must match before experimental results are trusted.
"""
from bank_only_probe import ROOT,OUT,AUDIT,PRIOR,read,save
import argparse,copy,hashlib,time
from collections import OrderedDict
from dataclasses import replace
import numpy as np,cv2
from PIL import Image
from model_manager import ModelManager
import example_audit_policy as policy

class CachedSession:
    """Exact ONNX tensor memoization, no reuse of scores or decisions."""
    def __init__(self,session):self.session=session;self.cache=OrderedDict();self.fresh=0;self.hits=0
    def __getattr__(self,name):return getattr(self.session,name)
    def run(self,outputs,inputs):
        assert outputs is None and len(inputs)==1
        a=next(iter(inputs.values()));key=hashlib.sha256(a.tobytes()).hexdigest()
        if key in self.cache:self.hits+=1;self.cache.move_to_end(key);return self.cache[key]
        v=self.session.run(outputs,inputs);self.fresh+=1;self.cache[key]=v
        if len(self.cache)>1800:self.cache.popitem(last=False)
        return v

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--photo');parser.add_argument('--label');parser.add_argument('--arms',default='original,normal_add1,positive_clean3,clean3_normal_add1');args=parser.parse_args()
    cv2.setNumThreads(4);plan=read(PRIOR/'plan.json');snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error
    b=ROOT/'workspace/dino-4r-visible-screw-20261106';policy.configure(np.load(b/'visible-part-bank.npz')['bank'],read(b/'v3/experiment-plan.json'),np.load(AUDIT/'letterbox-112-bank.npz')['bank'])
    arms=args.arms.split(',');banks={k:np.load(OUT/f'{k}-bank.npz')['bank'] for k in arms}
    cases={c['key']:c for c in read(PRIOR/'cases.json')};items=sorted(plan['items'],key=lambda x:(x['label']!='NG',x['key']))
    for item in items:
        key=item['key']
        if args.photo and key!=args.photo:continue
        if args.label and item['label']!=args.label:continue
        folder=PRIOR/'runs'/key;dest=OUT/'replay'/key;dest.mkdir(parents=True,exist_ok=True)
        if all((dest/f'{arm}.json').exists() for arm in arms):continue
        r=read(folder/'result.json');cs=sorted(r['candidates']+r['filtered_candidates'],key=lambda c:c['id']);ref,tar=[np.asarray(Image.open(folder/f'{k}.png').convert('L'),np.float32)/255 for k in ('reference','aligned')]
        cache=CachedSession(snap.session);start=time.perf_counter()
        for arm in arms:
            if (dest/f'{arm}.json').exists():continue
            m=copy.deepcopy(snap.manifest)
            extra_ids=['human-confirmed-ng128-22','known-good-Golden-speaker-boundary']
            m['example_bank']['normal']['ids'].extend(extra_ids[:len(banks[arm])-112])
            s=replace(snap,manifest=m,feature_bank=banks[arm],session=cache);objects=policy.Objects(ref,tar,cs);preds={};changes=[];baseline_mismatches=[]
            for c in cs:
                pred=policy.classify(s,ref,tar,c,objects);assert pred.get('status')=='active';preds[str(c['id'])]=pred
                old=c['classification']
                if arm=='original':
                    # Core decisions, model inputs, canonical geometry and pair
                    # scores must reconstruct. All other metadata is reported.
                    core=lambda p:(p['filter_recommendation'],p['canonical_object']['box'],p['paired_evidence'])
                    if core(pred)!=core(old):baseline_mismatches.append(c['id'])
                if pred['filter_recommendation']!=old['filter_recommendation']:changes.append(c['id'])
            hits=sorted({a for c in cs if preds[str(c['id'])]['filter_recommendation']=='keep' for a in cases[f'{key}-{c["id"]}']['answers']})
            unmatched=sum(preds[str(c['id'])]['filter_recommendation']=='keep' and not cases[f'{key}-{c["id"]}']['answers'] for c in cs)
            result=dict(key=key,arm=arm,predictions=preds,kept=sum(p['filter_recommendation']=='keep' for p in preds.values()),hits=hits,unmatched=unmatched,changed_candidates=changes,baseline_mismatches=baseline_mismatches)
            save(dest/f'{arm}.json',result);print('REPLAY',key,arm,'keep',result['kept'],'hits',len(hits),'outside',unmatched,'changes',changes,'baseline mismatches',baseline_mismatches,flush=True)
            assert not baseline_mismatches,('Baseline reconstruction differs; do not use results',key,baseline_mismatches)
        save(dest/('complete-'+ '-'.join(arms)+'.json'),dict(arms=arms,fresh_onnx=cache.fresh,exact_tensor_reuse=cache.hits,seconds=round(time.perf_counter()-start,2),base_result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()))
if __name__=='__main__':main()
