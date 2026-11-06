"""Reclassification under proposal perturbations and aligned-image resampling."""
from integrated_bank_replay import *
from correspondence_stability_probe import variations

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',required=True);ap.add_argument('--pair-only',action='store_true');a=ap.parse_args();cv2.setNumThreads(4)
    orig=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not orig.error
    review,normal=configure();classifier=integrated if a.arm.endswith('_review') else policy;groups=[]
    if not a.pair_only:
        for z in read(ROOT/'workspace/dino-4r-stability-20261106/perturbation-results.json')['pairs']:
            groups.append(dict(photo='ng-'+z['pair']['photo'],seeds=[int(z['pair'][k].split('-')[1]) for k in ('kept','excluded')],kind='original_conflict',answers=z['pair']['same_answer_ids']))
    groups += [dict(photo='ng-128',seeds=[cid],kind='normal_connector',expected='exclude') for cid in (22,40)]
    if not a.pair_only:groups += [dict(photo=p,seeds=[cid],kind='human_confirmed_screw',expected='keep') for p,cid in [('ng-128',10),('ng-135',88)]]
    alltests=[];scaled=[];records=[]
    for photo in sorted(set(g['photo'] for g in groups)):
        folder=PRIOR/'runs'/photo;r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];idx={c['id']:c for c in cs};ref,tar=[np.asarray(Image.open(folder/f'{n}.png').convert('L'),np.float32)/255 for n in ('reference','aligned')];cache=CachedSession(orig.session);fc=FeatureCache(photo)
        for module in (dino,policy,visible,terminal):module.features=fc.features
        s=snapshot(orig,a.arm,cache);obj=policy.Objects(ref,tar,cs)
        for g in [g for g in groups if g['photo']==photo]:
            before=classifier.classify(s,ref,tar,idx[g['seeds'][0]],obj);expected_pred,_=terminal.apply(s,ref,tar,before,review,normal);expected=g.get('expected',expected_pred['filter_recommendation']);extent=expected_pred['canonical_object']['box'];tests=[];images=[]
            for cid in g['seeds']:
                seed=idx[cid]
                for query,settings in variations(seed):
                    before=classifier.classify(s,ref,tar,query,obj);pred,_=terminal.apply(s,ref,tar,before,review,normal);z=dict(photo=photo,seed=cid,**settings,verdict=pred['filter_recommendation'],upstream_verdict=before['filter_recommendation'],expected=expected,canonical_box=pred['canonical_object']['box'],same_object=pred['canonical_object']['box']==extent,pass_test=pred['filter_recommendation']==expected and pred['canonical_object']['box']==extent);tests.append(z)
                for scale in (.75,.9,1.,1.1,1.25):
                    rr,tt=[cv2.resize(arr,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC).clip(0,1) for arr in (ref,tar)];support=[]
                    for c in cs:
                        if c.get('recovery')=='r4_visible_part':continue
                        q=copy.deepcopy(c)
                        for k in ('x','y','w','h'):q[k]=max(1,round(c[k]*scale))
                        q['area']=round(q['area']*scale*scale);support.append(q)
                    o=policy.Objects(rr,tt,support);q=next(c for c in support if c['id']==cid);before=classifier.classify(s,rr,tt,q,o);pred,_=terminal.apply(s,rr,tt,before,review,normal);images.append(dict(photo=photo,seed=cid,scale=scale,verdict=pred['filter_recommendation'],expected=expected,pass_test=pred['filter_recommendation']==expected,upstream_verdict=before['filter_recommendation'],paired_evidence=pred['paired_evidence']))
            alltests+=tests;scaled+=images;records.append(dict(g,expected=expected,query_pass=sum(z['pass_test'] for z in tests),query_total=len(tests),image_pass=sum(z['pass_test'] for z in images),image_total=len(images)))
            print('PROOF',a.arm,photo,g['seeds'],'query',records[-1]['query_pass'],'/',len(tests),'image',records[-1]['image_pass'],'/',len(images),flush=True)
        fc.save(photo)
    save(OUT/f'stability-{a.arm}{"-pair-only" if a.pair_only else ""}.json',dict(arm=a.arm,groups=records,query_tests=alltests,image_resample_tests=scaled,query_passed=all(z['pass_test'] for z in alltests),image_resample_passed=all(z['pass_test'] for z in scaled),scope='Classification re-executed; identical inputs may reuse exact feature/tensor cache. Proposal translation +/-4px, scale75/90/100/110/125%; aligned-image resampling with scaled existing support, no new proposals. Unannotated conflicts test consistency, not new human labels.',terminal_rule_unchanged=True))
if __name__=='__main__':main()
