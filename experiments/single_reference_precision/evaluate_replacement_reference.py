"""Swap one MPT12 reference; retain V9 and threshold, compare common targets."""
import sys,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2,numpy as np
from detector import read,register,refine,structure_mask,machine_mask,proposals,prioritize,DETECTOR_VERSION

ROOT=Path('workspace/windows-check/diagnostics/collected-data')
OUT=ROOT/'replacement-reference'
REFERENCE='cnd64409qy.tiff'  # Fixed before measuring the new results; shown in the prior report.

def evaluate(item):
    cv2.setNumThreads(2)
    folder=OUT/item['sha256'];folder.mkdir(parents=True,exist_ok=True)
    try:
        ref=read(item['reference']);ref=cv2.resize(ref,None,fx=1536/max(ref.shape),fy=1536/max(ref.shape))
        reg=register(ref,read(item['path']));mask=machine_mask(ref)&reg['valid']
        coverage=float(mask.sum()/machine_mask(ref).sum())
        if coverage<.95:raise ValueError('incomplete coverage')
        target,flow,regions=refine(ref,reg['aligned'],structure_mask(ref)&reg['valid'])
        changes=[];cs,_=proposals(ref,target,mask,.13,changes)
        np.savez_compressed(folder/'aligned.npz',ref=ref,target=target,mask=mask)
        result=dict(item,version=DETECTOR_VERSION,threshold=.13,count=len(cs),candidates=cs,
                    high=sum(not prioritize(c) for c in cs),structure_changes=changes,
                    regions=regions,inliers=reg['inliers'],coverage=coverage,
                    rotation=reg['rotation'],mirrored=reg['mirrored'],matrix=reg['matrix'].tolist())
    except Exception as error:result=dict(item,error=str(error))
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return {k:result[k] for k in ('relative','count','error') if k in result}

def main():
    OUT.mkdir(exist_ok=True)
    inv=json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'))
    items=[r for r in inv if r['relative'].startswith('MPT12/OK/')]
    reference=next(r for r in items if Path(r['path']).name==REFERENCE)
    targets=[dict(r,reference=reference['path']) for r in items if r['sha256']!=reference['sha256']]
    (OUT/'plan.json').write_text(json.dumps(dict(reference=reference,threshold=.13,version=DETECTOR_VERSION,
        selection='Fixed previously displayed alternative, not selected by minimum candidate count',items=targets),ensure_ascii=False,indent=2),encoding='utf-8')
    pending=[r for r in targets if not (OUT/r['sha256']/'result.json').exists()]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for n,result in enumerate(pool.map(evaluate,pending),1):print(n,len(pending),result,flush=True)
    print('COMPLETE',len(targets),flush=True)

if __name__=='__main__':main()
