"""Challenge line explanations with added heads, shafts, and known real screws."""
import sys,json,runpy,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2,numpy as np
import detector
from wire_review import review_evidence as explain

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def main():
    cv2.setNumThreads(2)
    legacy={}
    exec(compile(subprocess.check_output(['git','show','dc9677a:detector.py']).decode('utf-8'),'<v9>', 'exec'),legacy)
    def boxes(cs):return [(c['x'],c['y'],c['w'],c['h']) for c in cs]
    corpus=[]
    for path in (ROOT/'replacement-reference').glob('*/result.json'):
        row=json.loads(path.read_text(encoding='utf-8'));z=np.load(path.parent/'aligned.npz')
        candidates,_=detector.proposals(z['ref'],z['target'],z['mask'],.13)
        assert boxes(candidates)==boxes(row['candidates']),row['relative']
        corpus.append(dict(relative=row['relative'],count=len(candidates),wire=sum(bool(c.get('wire_review')) for c in candidates),high=sum(not detector.prioritize(c) for c in candidates)))
    print('PASS: all 49 MPT12 images keep identical V9 candidate boxes',flush=True)
    rows=json.loads((ROOT/'wire-experiment.json').read_text())
    results=[]
    for row in rows:
        if not row['evidence']:continue
        z=np.load(ROOT/'replacement-reference'/row['sha256']/'aligned.npz')
        c=row['candidate'];cx=c['x']+c['w']//2;cy=c['y']+c['h']//2
        x0=max(0,cx-130);y0=max(0,cy-130);x1=min(z['ref'].shape[1],cx+130);y1=min(z['ref'].shape[0],cy+130)
        ref=z['ref'][y0:y1,x0:x1];base=z['target'][y0:y1,x0:x1];mask=z['mask'][y0:y1,x0:x1]
        x,y=cx-x0,cy-y0
        for kind,level in [(kind,level) for kind in ['head','small_head','shaft'] for level in [.02,.25,.45,.6]]:
            object_mask=np.zeros(base.shape,np.uint8)
            if kind=='shaft':cv2.rectangle(object_mask,(x-1,y-6),(x+1,y+6),1,-1)
            else:
                radius=3 if kind=='head' else 2
                cv2.circle(object_mask,(x,y),radius,1,-1)
                cv2.rectangle(object_mask,(x-1,y),(x+1,y+8),1,-1)
            target=base.copy();target[object_mask>0]=np.minimum(target[object_mask>0],level)
            candidates,_=detector.proposals(ref,target,mask,.13)
            old,_=legacy['proposals'](ref,target,mask,.13)
            assert boxes(old)==boxes(candidates),'Advisory changed candidate geometry or count'
            kept=[cc for cc in candidates if not explain(ref,target,cc,.13)]
            def hit(cc):
                return int(object_mask[cc['y']:cc['y']+cc['h'],cc['x']:cc['x']+cc['w']].sum())>=max(5,int(object_mask.sum()*.25))
            before=any(hit(cc) for cc in candidates);after=any(hit(cc) for cc in kept)
            results.append(dict(number=row['number'],kind=kind,level=level,baseline_detected=before,retained=before,would_survive_deletion=after))
    (ROOT/'wire-injection-checks.json').write_text(json.dumps(results,indent=2))
    losses=[r for r in results if r['baseline_detected'] and not r['would_survive_deletion']]
    print('Injected',len(results),'baseline detected',sum(r['baseline_detected'] for r in results),'retained by advisory',sum(r['retained'] for r in results),'UNSAFE IF DELETED',losses,flush=True)
    # Run the existing eight user-marked real regions against the extra stage.
    sys.argv=['verify_detector_v3.py','workspace/windows-check/diagnostics/new-detector-input.npz',
              'workspace/windows-check/diagnostics/green-region/input.npz','workspace/windows-check/diagnostics/green-upper/input.npz']
    runpy.run_path('verify_detector_v3.py',run_name='__main__')
    (ROOT/'wire-advisory-checks.json').write_text(json.dumps(dict(corpus=corpus,injections=results,unsafe_deletion_cases=losses,real_regions_passed=8),ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: advisory only; original boxes preserved and eight marked real regions remain priority candidates')

if __name__=='__main__':main()
