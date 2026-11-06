"""Test background-reference role and existing core views before full replay."""
from integrated_bank_replay import *
from integrated_bank_probe import NEW

def main():
    f=np.load(OUT/'curated_v3-bank.npz');base=f['bank'];ids=f['ids'].tolist();n=int(f['n']);cores=np.load(NEW/'collection/core-bank.npz');ci=cores['ids'].tolist();context=np.load(NEW/'collection/context-bank.npz')['bank']
    noG=[i for i,z in enumerate(ids) if not z.startswith('G')];np.savez_compressed(OUT/'structural_normals-bank.npz',bank=base[noG],n=n,ids=np.array([ids[i] for i in noG]))
    b=base.copy();b[ids.index('G06')]=cores['bank'][ci.index('G06')];np.savez_compressed(OUT/'G06_core-bank.npz',bank=b,n=n,ids=np.array(ids))
    for ident in ('P05','P01'):
        b=np.concatenate([base[:n],cores['bank'][ci.index(ident)][None],base[n:]]);ii=ids[:n]+[ident]+ids[n:];np.savez_compressed(OUT/f'add_{ident}_core-bank.npz',bank=b,n=n+1,ids=np.array(ii))
    b=np.load(OUT/'G06_core-bank.npz')['bank'].copy();b[ids.index('S05')]=np.load(OUT/'original-bank.npz')['bank'][4];np.savez_compressed(OUT/'curated_v5-bank.npz',bank=b,n=n,ids=np.array(ids))
    cv2.setNumThreads(4);s0=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not s0.error;review,normal=configure();records=[]
    for photo,cids in [('ng-131',[65]),('ng-128',[7,22,40]),('ng-129',[12,56]),('ng-130',[9,25,100]),('ng-132',[13,137])]:
        folder=PRIOR/'runs'/photo;r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];ref,tar=[np.asarray(Image.open(folder/f'{k}.png').convert('L'),np.float32)/255 for k in ('reference','aligned')];cache=CachedSession(s0.session);fc=FeatureCache(photo)
        for module in (dino,policy,visible,terminal):module.features=fc.features
        for arm in ('curated_v3','curated_v4','curated_v5'):
            s=snapshot(s0,arm,cache);obj=policy.Objects(ref,tar,cs)
            for cid in cids:
                c=next(c for c in cs if c['id']==cid);before=policy.classify(s,ref,tar,c,obj);p,_=terminal.apply(s,ref,tar,before,review,normal);records.append(dict(photo=photo,id=cid,arm=arm,upstream_verdict=before['filter_recommendation'],final_verdict=p['filter_recommendation'],full_prediction=p));print('ROLE',photo,cid,arm,before['filter_recommendation'],p['filter_recommendation'],flush=True)
        fc.save(photo)
    save(OUT/'reference-role-counterfactuals-v5.json',records)
if __name__=='__main__':main()
