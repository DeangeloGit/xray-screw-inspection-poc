"""Capture exact pre-proposal arrays without changing the pilot's decisions."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    base=a.baseline.resolve();out=a.output.resolve();out.mkdir(exist_ok=True)
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');os.environ['XRAY_OVERKILL_PILOT']='1'
    sys.path.insert(0,str(ROOT))
    import cv2,detector
    from model_manager import ModelManager
    from answered_batch_run import sha,save
    cv2.setNumThreads(4)
    plan=json.loads((base/'plan.json').read_text(encoding='utf-8'))
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested'])
    assert snap.identity==plan['model']['fingerprint'] and not snap.error
    original=detector.proposals
    current={}
    def capture(ref,target,mask,threshold,*args,**kwargs):
        np.savez_compressed(out/'arrays'/f'{current["key"]}.npz',ref=ref,target=target,mask=mask)
        return original(ref,target,mask,threshold,*args,**kwargs)
    detector.proposals=capture
    (out/'arrays').mkdir(exist_ok=True)
    for row in plan['items']:
        key=row['key'];current['key']=key
        folder=out/'trace-runs'/key
        if (folder/'verified.json').exists():continue
        t=time.perf_counter()
        r=detector.detect(Path(plan['source'])/'Golden.tiff',row['path'],key,.13,model_snapshot=snap,output_directory=folder)
        old=json.loads((base/'runs'/'pilot'/key/'result.json').read_text(encoding='utf-8'))
        for field in ('candidates','filtered_candidates','matrix','local_alignment'):
            assert r[field]==old[field],(key,field)
        save(folder/'verified.json',dict(exact_pilot_result_reproduced=True,seconds=round(time.perf_counter()-t,2),arrays_sha256=sha(out/'arrays'/f'{key}.npz')))
        print('TRACE',key,len(r['candidates']),round(time.perf_counter()-t,2),flush=True)
    assert all(sha(p)==v for p,v in plan['hashes'].items())
    save(out/'trace-complete.json',dict(complete=True,photos=len(plan['items']),protected_inputs_unchanged=True))


if __name__=='__main__':main()
