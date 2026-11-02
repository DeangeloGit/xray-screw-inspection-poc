"""Verify the transport guard and audit recorded dataset removals."""
import json
from pathlib import Path
import cv2
import numpy as np
from transport_evidence import explain

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def run():
    ref=np.full((240,240),.85,np.float32)
    cv2.rectangle(ref,(80,90),(87,100),.15,-1);ref[90:94,80:83]=.4
    c=dict(x=100,y=90,w=8,h=11)
    moved=ref.copy();moved[90:101,100:108]=ref[90:101,80:88];moved[90:101,80:88]=.85
    added=ref.copy();added[90:101,100:108]=ref[90:101,80:88]
    assert explain(ref,moved,c,.13)
    assert explain(ref,added,c,.13) is None,'existing screw erased the added screw'
    darker=moved.copy();darker[90:101,100:108]=.01
    assert explain(ref,darker,c,.13) is None,'extra attenuation explained as movement'
    totals={}
    for method in ['context-consensus','blur','line-context','transport','tone-curve']:
        rows=json.loads((ROOT/(method+'-experiment.json')).read_text(encoding='utf-8'))
        assert len(rows)==185
        assert all(not r['removed'] for r in rows if '/NG/' in r['relative'])
        count=0
        if method=='transport':
            for row in rows:
                if not row['removed']:continue
                z=np.load(row['alignment'])
                for c in row['removed']:
                    target=z['target'].copy();x,y,w,h=[c[k] for k in ('x','y','w','h')]
                    target[y:y+h,x:x+w]=np.clip(target[y:y+h,x:x+w]-.3,0,1)
                    assert explain(z['ref'],target,c,.13) is None
                    count+=1
        totals[method]=dict(images=len(rows),ng_candidates_removed=0,extra_attenuation_checks=count)
    (ROOT/'precision-research-checks.json').write_text(json.dumps(totals,indent=2))
    print('PASS: moved object versus added copy, extra attenuation, 185 cases per method; no recorded NG candidates removed')

if __name__=='__main__':run()
