"""Replay the terminal review on all 100 frozen images/candidate decisions.
Alignment/proposal/base inference is reused, not claimed freshly recomputed.
All eligible retained whole-object decisions receive fresh DINO inference.
"""
from connector_probe import ROOT,OUT,AUDIT,PRIOR,read,save
import copy,hashlib,shutil,time
import numpy as np,cv2
from PIL import Image
from model_manager import ModelManager
from dino_paired_optimized import adjusted_image
import connector_policy as policy
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    cv2.setNumThreads(4);plan=copy.deepcopy(read(PRIOR/'plan.json'))
    frozen=dict(plan['hashes'])
    for p in [ROOT/'experiments/dino'/s for s in ('connector_policy.py','connector_probe.py','connector_run.py')]+[OUT/'normal-connector-bank.npz',OUT/'human-confirmations.json',AUDIT/'letterbox-112-bank.npz']:
        frozen[str(p)]=sha(p)
    for row in plan['items']:
        for name in ('result.json','reference.png','aligned.png','source.png'):
            p=PRIOR/'runs'/row['key']/name;frozen[str(p)]=sha(p)
    plan.update(hashes=frozen,policy=policy.VERSION,scope='Development regression. Frozen 100-image alignment/proposals/base decisions reused; fresh terminal DINO review of all eligible keeps. Normal training example: ng-128 #22 only. #40 was seen, not blind. No production deployment.')
    save(OUT/'plan.json',plan)
    for name in ('source-inventory.json','example-source-overlap.json'):shutil.copy2(PRIOR/name,OUT/name)
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error and snap.identity==plan['model']['fingerprint']
    bank=np.load(AUDIT/'letterbox-112-bank.npz')['bank'];n=np.load(OUT/'normal-connector-bank.npz');normal=dict(bank=n['bank'],aspect=float(n['aspect']));audit=[]
    for i,item in enumerate(plan['items'],1):
        key=item['key'];src=PRIOR/'runs'/key;dest=OUT/'runs'/key;dest.mkdir(parents=True,exist_ok=True)
        r=read(src/'result.json');cs=r['candidates']+r['filtered_candidates'];baseline={str(c['id']):copy.deepcopy(c['classification']) for c in cs}
        ref,tar=[np.asarray(Image.open(src/f'{k}.png').convert('L'),np.float32)/255 for k in ('reference','aligned')]
        if key=='ng-128':
            c=next(c for c in cs if c['id']==40);x,y,w,h=c['classification']['canonical_object']['box'];im=adjusted_image(snap.manifest,tar[y-12:y+h+12,x-12:x+w+12]);assert hashlib.sha256(im.tobytes()).hexdigest()==c['classification']['paired_evidence']['target']['input_sha256']
        changed=[];checks=[];start=time.perf_counter()
        for c in cs:
            pred,check=policy.apply(snap,ref,tar,c['classification'],bank,normal)
            if check is not None:checks.append(dict(id=c['id'],**check))
            if pred['filter_recommendation']!=c['classification']['filter_recommendation']:changed.append(c['id'])
            c['classification']=pred
        r['candidates']=[c for c in cs if c['classification']['filter_recommendation']=='keep'];r['filtered_candidates']=[c for c in cs if c['classification']['filter_recommendation']!='keep']
        r.update(proposal_count=len(r['candidates']),filtered_count=len(r['filtered_candidates']),high_count=sum(c['priority']=='high' for c in r['candidates']),wire_review_count=sum(bool(c.get('wire_review')) for c in r['candidates']),experimental_policy=policy.VERSION)
        r['review_count']=r['proposal_count']-r['high_count']
        for name in ('source.png','reference.png','aligned.png'):shutil.copy2(src/name,dest/name)
        source=cv2.imdecode(np.fromfile(str(src/'source.png'),np.uint8),cv2.IMREAD_COLOR);high=source.copy();all_overlay=source.copy()
        for c in r['candidates']:
            pts=np.rint(np.asarray(c['source_polygon'])*r['preview_scale']).astype('int32');color=(60,65,245) if c['priority']=='high' else (0,185,245)
            for canvas in ([high,all_overlay] if c['priority']=='high' else [all_overlay]):
                cv2.polylines(canvas,[pts],True,color,2);cv2.putText(canvas,str(c['id']),tuple(pts.min(axis=0)-[0,6]),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
        for name,im in [('overlay',high),('all_overlay',all_overlay)]:cv2.imencode('.png',im)[1].tofile(str(dest/f'{name}.png'))
        save(dest/'result.json',r);save(dest/'baseline79-classifications.json',baseline);save(dest/'normal-review.json',checks)
        save(dest/'complete.json',dict(key=key,result_sha256=sha(dest/'result.json'),baseline_sha256=sha(dest/'baseline79-classifications.json'),changed_candidates=changed,fresh_review_candidates=len(checks),seconds=round(time.perf_counter()-start,2)))
        audit.append(dict(key=key,changed=changed,reviewed=len(checks)));print('REVIEW',i,key,'fresh',len(checks),'removed',changed,flush=True)
    assert all(sha(__import__('pathlib').Path(p))==h for p,h in frozen.items())
    save(OUT/'run-complete.json',dict(complete=True,photos=100,fresh_full_detection=False,fresh_terminal_review=True,base_alignment_proposals_reused=True,source_and_production_hashes_unchanged=True,audit=audit))
if __name__=='__main__':main()
