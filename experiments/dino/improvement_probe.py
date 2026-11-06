"""Score image-derived proposals on both images; answers are not loaded."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);p.add_argument('--probe-name',default='probe');p.add_argument('--reuse',default='probe');p.add_argument('--pads',default='4,8');a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve();pads=[int(v) for v in a.pads.split(',')]
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');sys.path.insert(0,str(ROOT))
    import cv2,detector
    from model_manager import ModelManager
    from improvement_policy import supplemental,scores,extra_geometry
    cv2.setNumThreads(4);plan=read(base/'plan.json')
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested'])
    assert snap.identity==plan['model']['fingerprint']
    (out/a.probe_name).mkdir(exist_ok=True)
    for item in plan['items']:
        key=item['key'];dest=out/a.probe_name/f'{key}.json'
        if dest.exists():continue
        t=time.perf_counter();arr=np.load(out/'arrays'/f'{key}.npz');ref,tar,mask=[arr[k] for k in ('ref','target','mask')]
        old=read(base/'runs'/'pilot'/key/'result.json');previous=old['candidates']+old['filtered_candidates']
        new=supplemental(ref,tar,mask,detector.compensate_brightness(ref,tar),previous)
        for i,c in enumerate(new,len(previous)+1):c['id']=i
        r,targ=[(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in (ref,tar)]
        cachefile=out/a.reuse/f'{key}.json'
        cached={tuple(z['candidate'][k] for k in ('x','y','w','h')):z for z in read(cachefile)['items']} if cachefile.exists() else {}
        rows=[]
        for c in sorted(previous+new,key=lambda c:c['id']):
            existing=c['id']<=len(previous);keep=existing and c['classification']['filter_recommendation']=='keep'
            z=dict(id=c['id'],candidate=c,previous=existing,old_keep=keep)
            # Existing r3 keeps are immutable; score only pilot-added keeps and exclusions.
            is_r3=keep and 'overkill_pilot' not in c['classification']
            if not is_r3 and max(c['w'],c['h'])<=80:
                oldrow=cached.get(tuple(c[k] for k in ('x','y','w','h')),{})
                z['scores']={str(p):oldrow['scores'][str(p)] if str(p) in oldrow.get('scores',{}) else scores(snap,r,targ,c,p) for p in pads}
                z['geometry']=oldrow['geometry'] if 'geometry' in oldrow else extra_geometry(r,targ,c)
            rows.append(z)
        save(dest,dict(photo=key,items=rows,new_proposals=len(new),seconds=round(time.perf_counter()-t,2)))
        print('PROBE',key,'new',len(new),'scored',sum('scores' in z for z in rows),'seconds',round(time.perf_counter()-t,2),flush=True)


if __name__=='__main__':main()
