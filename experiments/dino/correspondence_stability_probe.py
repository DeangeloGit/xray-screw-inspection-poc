"""Fresh DINO checks of all conflict pairs and a fixed translation/scale grid."""
import argparse
import itertools
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')


def variations(c):
    for scale,dx,dy in itertools.product((.75,.9,1.,1.1,1.25),(-4,0,4),(-4,0,4)):
        w=max(4,round(c['w']*scale));h=max(4,round(c['h']*scale))
        yield dict(x=round(c['x']+c['w']/2-w/2)+dx,y=round(c['y']+c['h']/2-h/2)+dy,w=w,h=h),dict(scale=scale,dx=dx,dy=dy)


def fingerprint(pred):
    pair=pred['paired_evidence'];r4=pred.get('r4_experiment',{})
    return dict(verdict=pred['filter_recommendation'],pair={s:dict(label=pair[s]['label'],score=pair[s].get('screw_margin'),input_sha256=pair[s].get('input_sha256')) for s in ('reference','target')},extra_views={p:{s:v['input_sha256'] for s,v in view.items()} for p,view in r4.get('views',{}).items() if view is not None})


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('arrays',type=Path);p.add_argument('audit',type=Path);p.add_argument('output',type=Path);p.add_argument('--geometry-only',action='store_true');a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve();out.mkdir(exist_ok=True)
    os.environ['XRAY_WORKSPACE']=str(out/'runtime');os.environ['XRAY_CONFIG']=str(out/'isolated-settings.json');sys.path.insert(0,str(ROOT))
    import cv2
    from correspondence_policy import Objects,box,classify
    cv2.setNumThreads(4)
    if not a.geometry_only:
        from model_manager import ModelManager
        plan=read(base/'plan.json');snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot(plan['model']['requested']);assert not snap.error
    pairs=read(a.audit)['flagged_containment_pairs']+ [dict(photo='128',kept=f'128-{n}',excluded=f'128-{n}',same_answer_ids=[],user_flagged=True) for n in (10,80,82,103)];reports=[];allphotos=[]
    (out/'perturbations').mkdir(exist_ok=True)
    for key in [str(i) for i in range(128,138)]+['golden']:
        result=read(base/'runs/pilot'/key/'result.json');cs=result['candidates']+result['filtered_candidates'];idx={c['id']:c for c in cs}
        arr=np.load(a.arrays/f'{key}.npz');ref,tar=[arr[k] for k in ('ref','target')];qref,qtar=[(im*255).clip(0,255).astype('uint8').astype('float32')/255 for im in (ref,tar)]
        objects=Objects(qref,qtar,cs);geomidx={box(c):c for c in cs}
        allphotos.append(dict(photo=key,objects=len(objects.objects),items=[dict(id=c['id'],canonical_id=geomidx[box(objects.resolve(c)['canonical'])]['id'],object_id=objects.resolve(c)['object_id']) for c in cs]))
        for pair in [z for z in pairs if z['photo']==key]:
            name=pair['kept']+'__'+pair['excluded'];dest=out/'perturbations'/f'{name}.json'
            if dest.exists() and not a.geometry_only:reports.append(read(dest));continue
            small,big=[idx[int(pair[k].split('-')[1])] for k in ('kept','excluded')]
            object_small,object_big=[objects.resolve(c) for c in (small,big)]
            expected_object=object_small['object_id'];expected=None
            if not a.geometry_only:expected=fingerprint(classify(snap,ref,tar,small,objects))
            tests=[];t=time.perf_counter()
            for seed in ((small,) if small['id']==big['id'] else (small,big)):
                for query,settings in variations(seed):
                    obj=objects.resolve(query)
                    row=dict(seed_id=seed['id'],query=query,**settings,object_id=obj['object_id'] if obj else None,same_object=bool(obj and obj['object_id']==expected_object))
                    if not a.geometry_only:
                        pred=classify(snap,ref,tar,query,objects) if obj else None
                        proof=fingerprint(pred) if pred else None
                        row.update(prediction=proof,same_prediction=proof==expected)
                    tests.append(row)
            record=dict(pair=pair,canonical_box=list(box(object_small['canonical'])),same_object_before_perturbation=object_small['object_id']==object_big['object_id'],expected=expected,tests=tests,stable_object_tests=sum(z['same_object'] for z in tests),stable_prediction_tests=sum(z.get('same_prediction',False) for z in tests),total_tests=len(tests),seconds=round(time.perf_counter()-t,2))
            reports.append(record)
            if not a.geometry_only:save(dest,record)
            print(name,'object',record['stable_object_tests'],'prediction',record['stable_prediction_tests'],'/',len(tests),'seconds',record['seconds'],flush=True)
    save(out/('geometry-screen.json' if a.geometry_only else 'perturbation-results.json'),dict(photos=allphotos,pairs=reports,total_tests=sum(r['total_tests'] for r in reports),stable_object_tests=sum(r['stable_object_tests'] for r in reports),stable_prediction_tests=sum(r['stable_prediction_tests'] for r in reports),fresh_inference_per_test=not a.geometry_only,grid=dict(scales=[.75,.9,1,1.1,1.25],dx=[-4,0,4],dy=[-4,0,4])))


if __name__=='__main__':main()
