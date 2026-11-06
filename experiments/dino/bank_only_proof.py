"""Stability of curated main examples; no added terminal rule, no answer gate."""
from bank_only_probe import ROOT,OUT,AUDIT,PRIOR,read,save
from dataclasses import replace
import argparse,copy,numpy as np,cv2
from PIL import Image
from model_manager import ModelManager
import example_audit_policy as policy
from correspondence_stability_probe import variations
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--arm',default='positive_clean3');args=parser.parse_args()
    cv2.setNumThreads(4);original=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not original.error
    bank=np.load(OUT/f'{args.arm}-bank.npz')['bank'];manifest=copy.deepcopy(original.manifest)
    if len(bank)==113:manifest['example_bank']['normal']['ids'].append('human-confirmed-ng128-22')
    snap=replace(original,manifest=manifest,feature_bank=bank);b=ROOT/'workspace/dino-4r-visible-screw-20261106'
    policy.configure(np.load(b/'visible-part-bank.npz')['bank'],read(b/'v3/experiment-plan.json'),np.load(AUDIT/'letterbox-112-bank.npz')['bank'])
    folder=PRIOR/'runs/ng-128';r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];ref,tar=[np.asarray(Image.open(folder/f'{k}.png').convert('L'),np.float32)/255 for k in ('reference','aligned')];objects=policy.Objects(ref,tar,cs);tests=[];scaled=[]
    for cid in (22,40):
        seed=next(c for c in cs if c['id']==cid);expected=seed['classification']['canonical_object']['box']
        for query,settings in variations(seed):
            pred=policy.classify(snap,ref,tar,query,objects);tests.append(dict(id=cid,query=query,**settings,verdict=pred['filter_recommendation'],canonical_box=pred['canonical_object']['box'],same_object=pred['canonical_object']['box']==expected,input_sha256={s:p['input_sha256'] for s,p in pred['paired_evidence'].items()},fresh_inference=True))
        for scale in (.75,.9,1.,1.1,1.25):
            rr,tt=[cv2.resize(a,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC).clip(0,1) for a in (ref,tar)];support=[]
            for c in cs:
                if c.get('recovery')=='r4_visible_part':continue
                q=copy.deepcopy(c)
                for k in ('x','y','w','h'):q[k]=max(1,round(c[k]*scale))
                q['area']=round(q['area']*scale*scale);support.append(q)
            obj=policy.Objects(rr,tt,support);query=next(c for c in support if c['id']==cid);pred=policy.classify(snap,rr,tt,query,obj);scaled.append(dict(id=cid,scale=scale,verdict=pred['filter_recommendation'],canonical_box=pred['canonical_object']['box'],paired_evidence=pred['paired_evidence'],scope='existing full 79 classifier with scaled candidate support, no proposal regeneration'))
        print('BANK PROOF',cid,'queries',sum(t['verdict']=='exclude' and t['same_object'] for t in tests if t['id']==cid),'/45','images',sum(t['verdict']=='exclude' for t in scaled if t['id']==cid),'/5',flush=True)
    save(OUT/f'stability-{args.arm}.json',dict(arm=args.arm,query_tests=tests,image_resample_tests=scaled,query_passed=all(t['verdict']=='exclude' and t['same_object'] for t in tests),image_resample_passed=all(t['verdict']=='exclude' for t in scaled),extra_connector_rule_used=False,scope='90 fresh query tests, 10 resampled aligned-image tests using scaled existing support; no new scan or proposal rerun'))
if __name__=='__main__':main()
