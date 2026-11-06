"""Fresh upstream+terminal inference on query perturbations; resampling diagnosis."""
from connector_probe import ROOT,OUT,AUDIT,PRIOR,read,save
import numpy as np,cv2
from PIL import Image
from model_manager import ModelManager
import example_audit_policy as base
import connector_policy as policy
from correspondence_stability_probe import variations
def main():
    cv2.setNumThreads(4);snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    bank=np.load(AUDIT/'letterbox-112-bank.npz')['bank'];n=np.load(OUT/'normal-connector-bank.npz');normal=dict(bank=n['bank'],aspect=float(n['aspect']));b=ROOT/'workspace/dino-4r-visible-screw-20261106'
    base.configure(np.load(b/'visible-part-bank.npz')['bank'],read(b/'v3/experiment-plan.json'),bank)
    folder=PRIOR/'runs/ng-128';r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];ref,tar=[np.asarray(Image.open(folder/f'{k}.png').convert('L'),np.float32)/255 for k in ('reference','aligned')]
    objects=base.Objects(ref,tar,cs);tests=[];resampled=[]
    for cid in (22,40):
        c=next(c for c in cs if c['id']==cid);extent=c['classification']['canonical_object']['box']
        for query,settings in variations(c):
            before=base.classify(snap,ref,tar,query,objects);pred,review=policy.apply(snap,ref,tar,before,bank,normal)
            tests.append(dict(id=cid,query=query,**settings,verdict=pred['filter_recommendation'],canonical_box=pred['canonical_object']['box'],same_object=pred['canonical_object']['box']==extent,fresh_inference=True,input_sha256={k:v['input_sha256'] for k,v in pred['paired_evidence'].items()}))
        for scale in (.75,.9,1.,1.1,1.25):
            # Whole aligned images resampled, then expected object extent scaled.
            # This diagnoses classifier sensitivity, not a proposal rerun.
            rr,tt=[cv2.resize(a,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC).clip(0,1) for a in (ref,tar)];bb=[round(v*scale) for v in extent];check=policy.review(snap,rr,tt,bb,bank,normal)
            resampled.append(dict(id=cid,scale=scale,box=bb,exclude=check['exclude'],views=check['views']))
        print('PROOF',cid,'query exclude',sum(t['verdict']=='exclude' for t in tests if t['id']==cid),'/45','resample exclude',sum(t['exclude'] for t in resampled if t['id']==cid),'/5',flush=True)
    result=dict(query_tests=tests,image_resample_tests=resampled,query_passed=all(t['verdict']=='exclude' and t['same_object'] for t in tests),image_resample_passed=all(t['exclude'] for t in resampled),scope='90 fresh upstream+terminal query tests. 10 whole-aligned-image resamplings with scaled expected extent test terminal recognition only; no new scan or full proposal rerun.')
    save(OUT/'stability-proof.json',result)
if __name__=='__main__':main()
