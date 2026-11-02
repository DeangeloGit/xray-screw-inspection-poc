"""Evaluate candidate explanations, never load alternate normal images."""
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import cv2
import numpy as np
import sys, importlib
METHOD=sys.argv[1] if len(sys.argv)>1 else "transport"
MODULES={"context-consensus":"single_reference_research", "blur":"blur_evidence", "line-context":"line_context_evidence", "transport":"transport_evidence", "tone-curve":"tone_curve_evidence"}
explain=importlib.import_module(MODULES[METHOD]).explain

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def evaluate(path):
    cv2.setNumThreads(1)
    row=json.loads(path.read_text(encoding='utf-8'))
    sha=row['sha256'];alignment=path.parent/'aligned.npz'
    if not alignment.exists():return None
    data=np.load(alignment);ref,target=data['ref'],data['target']
    removed=[];kept=[]
    for candidate in row['candidates']:
        evidence=explain(ref,target,candidate,.13)
        if evidence:removed.append(dict(candidate,single_reference_evidence=evidence))
        else:kept.append(candidate)
    return dict(relative=row['relative'],sha256=sha,before=len(row['candidates']),after=len(kept),
                removed=removed,kept=kept,alignment=str(alignment),split=row.get('split','NG'))

def main():
    rows=list((ROOT/'cache').glob('*/baseline.json'))
    # Include images recovered by the mirror fix, without counting them as a
    # reduction from a registration failure.
    reflected=[p for p in (ROOT/'reflection').glob('*/result.json') if json.loads(p.read_text(encoding='utf-8')).get('mirrored')]
    replaced={p.parent.name for p in reflected}
    rows=[p for p in rows if p.parent.name not in replaced]+reflected
    results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(evaluate,rows):
            if result:
                results.append(result)
                print(result['relative'],result['before'],result['after'],flush=True)
    (ROOT/(METHOD+'-experiment.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
