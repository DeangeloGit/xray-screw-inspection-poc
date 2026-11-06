"""Evaluate fixed score variants AFTER image-only probe; preserve original answers."""
import argparse
import json
import os
from pathlib import Path
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')


def acceptance(z,kind,margin):
    if not z.get('scores') or any(z['scores'].get(p) is None for p in ('4','8')):return False
    for p in ('4','8'):
        pair=z['scores'][p]
        def score(s):
            v=pair[s]
            if kind=='wholelocal':return (v['whole']+v['local'])/2
            if kind=='localfocus':return (v['local']+v['focused'])/2
            return (v['whole']+v['local']+v['focused'])/3
        if not (score('reference')<0 and score('target')>=margin):return False
    return True


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);p.add_argument('--probe-name',default='probe');a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve()
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');sys.path.insert(0,str(ROOT))
    from detector import source_points
    from answered_batch_report import matches
    answers=read(base/'answers.json');rows=[]
    for f in sorted((out/a.probe_name).glob('*.json')):
        pool=read(f);key=pool['photo'];r=read(base/'runs'/'pilot'/key/'result.json');shape=np.load(out/'arrays'/f'{key}.npz')['ref'].shape
        flow=np.zeros((*shape,2),np.float32)
        for region in r['local_alignment']:
            x,y,X,Y=region['bbox'];flow[y:Y,x:X]=[region['dx'],region['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12)
        reg=dict(matrix=np.asarray(r['matrix']),rotation=r['rotation_ccw']//90,mirrored=r['mirrored_input'],target_scale=r['preview_scale'])
        marks=answers.get(key,{}).get('marks',[])
        for z in pool['items']:
            c=z['candidate'];x,y,w,h=[c[k] for k in ('x','y','w','h')];poly=source_points([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],reg,flow,r['source_shape'])
            hit,edge=matches(poly,marks);rows.append(dict(key=f'{key}-{z["id"]}',photo=key,answers=hit,edge_answers=edge,**z))
    variants=[]
    for kind in ('wholelocal','localfocus','three'):
        for margin in (0.,.01,.02,.03,.04):
            added=[z for z in rows if not z['old_keep'] and acceptance(z,kind,margin)]
            prior={(z['photo'],i) for z in rows if z['old_keep'] for i in z['answers']}
            found={(z['photo'],i) for z in added for i in z['answers']}
            variants.append(dict(kind=kind,margin=margin,added_candidates=len(added),new_answers=sorted(found-prior),new_answer_count=len(found-prior),added_unmatched=[z['key'] for z in added if not z['answers']],added_hits=[z['key'] for z in added if z['answers']]))
    save(out/'scored-candidates.json',rows);save(out/'variants.json',variants)
    for v in variants:print(v['kind'],v['margin'],'newanswers',v['new_answer_count'],'extra-unmatched',len(v['added_unmatched']),'added',v['added_candidates'],flush=True)
    print('ADDED OLD PILOT FEATURES')
    for z in rows:
        if z['old_keep'] and 'overkill_pilot' in z['candidate']['classification']:
            print(z['key'],z['answers'],[(k,[[round(v[t],3) for t in ('whole','local','focused')] for v in p.values()] if p else None) for k,p in z.get('scores',{}).items()],z.get('geometry',[]),flush=True)


if __name__=='__main__':main()
