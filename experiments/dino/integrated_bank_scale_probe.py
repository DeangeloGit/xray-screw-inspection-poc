"""Trace original and integrated decisions at a human-confirmed screw across scales."""
from integrated_bank_replay import *

def main():
    cv2.setNumThreads(4);photo='ng-135';cid=88
    orig=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not orig.error
    review,normal=configure();folder=PRIOR/'runs'/photo;r=read(folder/'result.json');cs=r['candidates']+r['filtered_candidates'];ref,tar=[np.asarray(Image.open(folder/f'{n}.png').convert('L'),np.float32)/255 for n in ('reference','aligned')]
    cache=CachedSession(orig.session);fc=FeatureCache(photo)
    for module in (dino,policy,visible,terminal):module.features=fc.features
    records=[]
    for scale in (.75,.9,1.,1.1,1.25):
        rr,tt=[cv2.resize(arr,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC).clip(0,1) for arr in (ref,tar)];support=[]
        for c in cs:
            if c.get('recovery')=='r4_visible_part':continue
            q=copy.deepcopy(c)
            for k in ('x','y','w','h'):q[k]=max(1,round(c[k]*scale))
            q['area']=round(q['area']*scale*scale);support.append(q)
        for arm in ('original','curated_v5_review'):
            s=snapshot(orig,arm,cache);o=policy.Objects(rr,tt,support);q=next(c for c in support if c['id']==cid);before=(integrated if arm.endswith('_review') else policy).classify(s,rr,tt,q,o);pred,_=terminal.apply(s,rr,tt,before,review,normal)
            records.append(dict(photo=photo,id=cid,scale=scale,arm=arm,query=q,upstream=before,final=pred));print(arm,scale,pred['filter_recommendation'],pred['decision_reason'],flush=True)
    save(OUT/'human88-scale-diagnosis.json',records);fc.save(photo)

if __name__=='__main__':main()
