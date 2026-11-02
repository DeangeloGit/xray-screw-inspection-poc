"""Synthetic retention checks, separate from real defect validation."""
import json
from pathlib import Path
import cv2
import numpy as np
from detector import proposals,machine_mask
from normal_variation import separate
ROOT=Path('workspace/windows-check/diagnostics/collected-data')


def run():
    # Identical normal appearance must be explainable; an added object must survive.
    ref=np.full((160,160),.8,np.float64)
    cv2.rectangle(ref,(30,30),(130,130),.25,5)
    cv2.line(ref,(50,50),(100,120),.4,4)
    c=dict(x=65,y=65,w=20,h=20)
    kept,removed=separate([c],ref,[('a',ref),('b',ref)],.13)
    assert removed and not kept
    target=ref.copy();cv2.circle(target,(75,75),7,.05,-1)
    assert separate([c],target,[('a',ref),('b',ref)],.13)[0]
    assert separate([c],ref,[('only-one',ref)],.13)[0]
    assert separate([c],ref,[('duplicate',ref),('duplicate',ref)],.13)[0]
    summaries=[]
    experiments=json.loads((ROOT/'normal-bank-experiment.json').read_text(encoding='utf-8'))
    inventory=json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'));lookup={r['relative']:r for r in inventory}
    for model in sorted({r['relative'].split('/')[0] for r in experiments}):
        cases=sorted((r for r in experiments if r['relative'].startswith(model+'/') and r['split']=='validation'),key=lambda r:r['relative'])[:2]
        for case in cases:
            z=np.load(ROOT/'cache'/case['sha256']/'aligned.npz');ref,target,mask=z['ref'],z['target'],z['mask']
            normals=[(lookup[path]['sha256'],np.load(ROOT/'cache'/lookup[path]['sha256']/'aligned.npz')['target']) for path in case['bank']]
            stable=(target>.7)&(ref>.7)&mask
            for _,normal in normals:stable &= normal>.7
            # Distributed bright locations with nearby structure, away from image borders.
            stable=cv2.erode(stable.astype('uint8'),np.ones((5,5),np.uint8))>0
            ys,xs=np.where(stable);order=np.lexsort((xs,ys));ys,xs=ys[order],xs[order]
            for index in np.linspace(0,len(xs)-1,6,dtype=int):
                x,y=int(xs[index]),int(ys[index]);modified=target.copy()
                cv2.ellipse(modified,(x,y),(5,9),0,0,360,.03,-1)
                candidates,_=proposals(ref,modified,mask,.13)
                kept,removed=separate(candidates,modified,normals,.13)
                def hit(items):return any(c['x']<x+6 and c['y']<y+10 and c['x']+c['w']>x-5 and c['y']+c['h']>y-9 for c in items)
                before,after=hit(candidates),hit(kept)
                if before:assert after,(case['relative'],x,y)
                summaries.append(dict(sample=case['relative'],center=[x,y],baseline_hit=before,retained=after))
    (ROOT/'synthetic-retention.json').write_text(json.dumps(summaries,indent=2))
    print('SYNTHETIC',len(summaries),'baseline hits',sum(r['baseline_hit'] for r in summaries),'retained',sum(r['retained'] for r in summaries),flush=True)
    print('PASS: two-reference requirement, matching normal, added object and optional dataset injections')


if __name__=='__main__':run()
