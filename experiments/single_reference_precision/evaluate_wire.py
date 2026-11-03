"""Audit the replacement-reference candidates and prior NG candidates."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2,numpy as np
from wire_review import review_evidence as explain

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def main():
    cv2.setNumThreads(2)
    items=json.loads((ROOT/'remaining-56/index.json').read_text(encoding='utf-8'))
    records=[];sha=None
    for row in items:
        if sha!=row['sha256']:
            sha=row['sha256'];z=np.load(ROOT/'replacement-reference'/sha/'aligned.npz')
            ref,target=z['ref'],z['target']
        evidence=explain(ref,target,row['candidate'],.13)
        records.append(dict(number=row['number'],sha256=sha,candidate=row['candidate'],evidence=evidence))
    (ROOT/'wire-experiment.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print('Explained:',[r['number'] for r in records if r['evidence']],flush=True)

if __name__=='__main__':main()
