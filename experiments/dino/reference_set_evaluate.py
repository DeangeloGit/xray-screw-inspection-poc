"""Reference-content experiment using identical previously cached query vectors."""
from reference_set_prepare import ROOT,OUT,PRIOR,read,save
import hashlib,time
import numpy as np
from PIL import Image
from model_manager import ModelManager
from dino_paired_optimized import example_features,validate_bank

def score(v,bank,n):
    sims=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
    margins=[float(np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean()) for s in sims]
    return dict(margin=sum(margins)/2,whole=margins[0],local=margins[1],positive_neighbors=[(np.argsort(s[:n])[-3:][::-1]+1).tolist() for s in sims],normal_neighbors=[(np.argsort(s[n:])[-3:][::-1]+1).tolist() for s in sims])

def main():
    import cv2
    cv2.setNumThreads(4)
    manifest=read(OUT/'collection/manifest.json')
    rows=manifest['examples'];main=[r for label in ('screw','non_screw') for r in rows if r['role']=='main_reference' and r['label']==label]
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='cpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    banks={'original':(snap.feature_bank,47)}
    for mode in ('core','context'):
        p=OUT/'collection'/f'{mode}-bank.npz';vectors=[]
        if p.exists():
            cached=np.load(p);assert str(cached['manifest_sha256'])==hashlib.sha256((OUT/'collection/manifest.json').read_bytes()).hexdigest();bank=cached['bank']
        else:
            for i,r in enumerate(main):
                v=r['views'][mode];assert hashlib.sha256(Path(v['file']).read_bytes()).hexdigest()==v['sha256']
                a=np.asarray(Image.open(v['file']).convert('L'),np.float32)/255
                vectors.append(example_features(snap.manifest,snap.session,a))
                print(mode,i+1,len(main),r['id'],flush=True)
            bank=np.stack(vectors)
            np.savez_compressed(p,bank=bank,n=8,ids=np.array([r['id'] for r in main]),manifest_sha256=hashlib.sha256((OUT/'collection/manifest.json').read_bytes()).hexdigest())
        assert bank.shape==(35,8,2,384) and np.allclose(np.linalg.norm(bank,axis=-1),1,atol=.001)
        banks['new_'+mode]=(bank,8)
        # Additional arm tests supplementation without discarding old poses.
        banks['old_plus_'+mode]=(np.concatenate([snap.feature_bank[:47],bank[:8],snap.feature_bank[47:],bank[8:]]),55)
    audit=ROOT/'workspace/dino-4r-example-audit-20261106';query=read(audit/'all-crop-bank-scores.json');cases={r['key']:r for r in read(PRIOR/'cases.json')};results=[]
    for photo in map(str,range(128,138)):
        cache=np.load(audit/'all-features'/f'{photo}.npz')
        for q in query:
            if q['photo']!=photo:continue
            pairs={s:cache[q['variants']['center-12-old'][s]['input_sha256']] for s in ('reference','target')};arms={}
            for name,(b,n) in banks.items():
                s={side:score(v,b,n) for side,v in pairs.items()};s['keep']=s['target']['margin']>=0 and s['reference']['margin']<0;arms[name]=s
            key=f'ng-{photo}-{q["id"]}';results.append(dict(key=key,photo=photo,id=q['id'],answers=cases[key]['answers'],input_sha256={s:q['variants']['center-12-old'][s]['input_sha256'] for s in pairs},arms=arms))
    summary=[]
    for split,selected in [('construction_128',[r for r in results if r['photo']=='128']),('development_holdout_129_137',[r for r in results if r['photo']!='128'])]:
        oldhits={(r['photo'],a) for r in selected if r['arms']['original']['keep'] for a in r['answers']}
        for name in banks:
            hits={(r['photo'],a) for r in selected if r['arms'][name]['keep'] for a in r['answers']}
            summary.append(dict(split=split,arm=name,raw_hits=len(hits),lost_vs_same_stage=sorted(oldhits-hits),added_vs_same_stage=sorted(hits-oldhits),unmatched=sum(r['arms'][name]['keep'] and not r['answers'] for r in selected),new_unmatched=[r['key'] for r in selected if not r['answers'] and r['arms'][name]['keep'] and not r['arms']['original']['keep']]))
    save(OUT/'fixed-query-scores.json',results);save(OUT/'fixed-query-summary.json',summary)
    print('SUMMARY',summary,flush=True)
    print('PAIR',[(r['id'],{a:round(v['target']['margin'],6) for a,v in r['arms'].items()}) for r in results if r['photo']=='128' and r['id'] in (22,40)],flush=True)
    save(OUT/'evaluation-scope.json',dict(query_candidates=len(results),provider='CPU',new_query_inference=False,identical_cached_query_vectors=True,main_bank_only=True,complete_pipeline_replayed=False,full100_new_bank_validated=False,part_bank_not_activated=True,production_changed=False,notes='Fixed center12 query; no connector veto or crop change. Raw hits are not full79 policy hits. Other nine scans are previous development data, not external independent scans.'))
if __name__=='__main__':
    from pathlib import Path
    main()
