"""Single-reference counterfactuals at the actual complete-classifier stage."""
from integrated_bank_replay import *
from integrated_bank_probe import NEW

def main():
    cv2.setNumThreads(4);s0=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not s0.error
    review,normal=configure();f=np.load(OUT/'clean3_integrated-bank.npz');ids=f['ids'].tolist();ix=[i for i,z in enumerate(ids) if z!='P11'];np.savez_compressed(OUT/'clean3_dedup-bank.npz',bank=f['bank'][ix],n=54,ids=np.array([ids[i] for i in ix]));records=[]
    for ident in ('P01','P04','P05','P11'):
        ix=[i for i,z in enumerate(ids) if z!=ident];np.savez_compressed(OUT/f'clean3_without_{ident}-bank.npz',bank=f['bank'][ix],n=54,ids=np.array([ids[i] for i in ix]))
    selected=np.load(OUT/'clean3_selective-bank.npz');selids=selected['ids'].tolist();ix=[i for i,z in enumerate(selids) if z not in ('G01','N12')];np.savez_compressed(OUT/'no_ambiguous_normals-bank.npz',bank=selected['bank'][ix],n=51,ids=np.array([selids[i] for i in ix]));core=np.load(NEW/'collection/core-bank.npz');bb=selected['bank'].copy();bb[selids.index('P06')]=core['bank'][core['ids'].tolist().index('P06')];np.savez_compressed(OUT/'P06_core_only-bank.npz',bank=bb,n=51,ids=np.array(selids))
    for photo,cids in [('ng-128',[7,22,40]),('ng-129',[12,56]),('ng-130',[25,100]),('ng-131',[65]),('ng-132',[13,137]),('ng-137',[14])]:
        folder=PRIOR/'runs'/photo;r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];ref,tar=[np.asarray(Image.open(folder/f'{n}.png').convert('L'),np.float32)/255 for n in ('reference','aligned')];cache=CachedSession(s0.session);fc=FeatureCache(photo)
        for module in (dino,policy,visible,terminal):module.features=fc.features
        for arm in ('clean3_integrated','clean2_integrated','clean3_without_P01','clean3_without_P04','clean3_without_P05','clean3_without_P11','clean2_dedup','clean3_selective','no_ambiguous_normals','P06_core_only','curated_v3'):
            s=snapshot(s0,arm,cache);obj=policy.Objects(ref,tar,cs)
            for cid in cids:
                c=next(c for c in cs if c['id']==cid);before=policy.classify(s,ref,tar,c,obj);p,_=terminal.apply(s,ref,tar,before,review,normal);records.append(dict(photo=photo,id=cid,arm=arm,upstream_verdict=before['filter_recommendation'],final_verdict=p['filter_recommendation'],paired_evidence=p['paired_evidence'],full_prediction=p));print('CAUSE',photo,cid,arm,before['filter_recommendation'],p['filter_recommendation'],flush=True)
        fc.save(photo)
    save(OUT/'complete-stage-counterfactuals.json',records)
if __name__=='__main__':main()
