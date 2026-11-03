"""Hypothetical deletion audit only; production retains every tagged candidate."""
import sys,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2,numpy as np
from wire_review import review_evidence as explain

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def check(row):
    cv2.setNumThreads(1)
    z=np.load(row['alignment']);ref,target=z['ref'],z['target']
    removed=[]
    for c in row['kept']:
        e=explain(ref,target,c,.13)
        if e:removed.append(dict(c,wire_evidence=e))
    return dict(relative=row['relative'],sha256=row['sha256'],before=len(row['kept']),after=len(row['kept'])-len(removed),removed=removed,alignment=row['alignment'])

def main():
    rows=json.loads((ROOT/'single-reference-experiment.json').read_text(encoding='utf-8'))
    rows=[r for r in rows if not r['relative'].startswith('MPT12/')]
    results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for r in pool.map(check,rows):results.append(r);print(r['relative'],r['before'],r['after'],flush=True)
    (ROOT/'wire-corpus.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
