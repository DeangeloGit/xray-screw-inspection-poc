"""Read-only dataset benchmark with reproducible per-machine references and cached alignment."""
import json
import hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import cv2
import numpy as np
import subprocess
BASELINE_COMMIT = 'd99a1c6'
_baseline = {'__name__':'collected_data_baseline'}
exec(compile(subprocess.check_output(['git','show',BASELINE_COMMIT+':detector.py']).decode('utf-8'), '<baseline-detector>', 'exec'), _baseline)
read, register, refine, structure_mask, machine_mask, proposals, prioritize, DETECTOR_VERSION = (
    _baseline[name] for name in ('read','register','refine','structure_mask','machine_mask','proposals','prioritize','DETECTOR_VERSION'))

ROOT=Path('workspace/windows-check/diagnostics/collected-data')


def evaluate(item):
    cv2.setNumThreads(2)
    path=ROOT/'cache'/item['sha256'];path.mkdir(parents=True,exist_ok=True)
    try:
        ref=read(item['reference']);ref=cv2.resize(ref,None,fx=1536/max(ref.shape),fy=1536/max(ref.shape))
        reg=register(ref,read(item['path']));mask=machine_mask(ref)&reg['valid']
        if mask.sum()/max(machine_mask(ref).sum(),1)<.95:raise ValueError('incomplete coverage')
        target,flow,regions=refine(ref,reg['aligned'],structure_mask(ref)&reg['valid'])
        changes=[];candidates,_=proposals(ref,target,mask,.13,changes)
        # Float64 preserves the exact baseline; cached images are private experiment artifacts.
        np.savez_compressed(path/'aligned.npz',ref=ref,target=target,mask=mask)
        result=dict(**item,version=DETECTOR_VERSION,threshold=.13,candidates=candidates,structure_changes=changes,
                    count=len(candidates),high=sum(not prioritize(c) for c in candidates),regions=regions,inliers=reg['inliers'])
    except Exception as e:result=dict(**item,error=str(e))
    (path/'baseline.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('candidates','structure_changes','regions')}


def main():
    inventory=json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'))
    references={}
    for model in {r['relative'].split('/')[0] for r in inventory}:
        ok=sorted((r for r in inventory if r['relative'].startswith(model+'/OK/')),key=lambda r:r['relative'])
        reference=next((r for r in ok if r['relative'].endswith('CND6440B6L_2026_11_02_16_59_36_95.tiff')),ok[0])
        references[model]=reference
    items=[]
    for row in inventory:
        model,label,*_=row['relative'].split('/')
        if row['sha256']==references[model]['sha256']:continue
        # User explicitly set aside the prior 17_14_35_98 case.
        if row['relative'].endswith('CND6440DTD_2026_11_02_17_14_35_98.tiff'):continue
        unit=Path(row['path']).stem.split('_')[0]
        split='validation' if int(hashlib.sha256(unit.encode()).hexdigest()[:8],16)%3==0 else 'development'
        items.append(dict(row,model=model,label=label,split=split,reference=references[model]['path']))
    (ROOT/'benchmark-plan.json').write_text(json.dumps(dict(baseline_commit=BASELINE_COMMIT,references=references,items=items),ensure_ascii=False,indent=2),encoding='utf-8')
    pending=[i for i in items if not (ROOT/'cache'/i['sha256']/'baseline.json').exists()]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for n,result in enumerate(pool.map(evaluate,pending),1):
            print(n,len(pending),result['relative'],result.get('count',result.get('error')),flush=True)
    print('BASELINE COMPLETE',len(items),flush=True)


if __name__=='__main__':main()


