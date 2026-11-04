"""Repeated one-photo A/B runs; no production configuration changes."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/dino-cpu-reuse-20261104'


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def protected():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    paths=[ROOT/n for n in names if n and not n.startswith('experiments/')]
    paths += [ROOT/'models/active.json', ROOT/'models/dino-paired-47-20261103/manifest.json',ROOT/'models/dino-paired-47-20261103/model.onnx',ROOT/'workspace/windows-check/state/ui_settings.json']
    paths += list((ROOT/'workspace/windows-check/outputs').rglob('*.json'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}


def compare(base,new):
    a,b=load(Path(base['result_path'])),load(Path(new['result_path']))
    fields=['matrix','rotation_ccw','mirrored_input','local_alignment','coverage','baseline_candidates','structure_changes','source_machine_bbox']
    changed=[field for field in fields if a[field]!=b[field]]
    def candidates(z):return {c['id']:c for k in ('candidates','filtered_candidates') for c in z[k]}
    ac,bc=candidates(a),candidates(b)
    assert set(ac)==set(bc)
    boxes=[];decisions=[]
    for i in ac:
        aa,bb=ac[i].copy(),bc[i].copy()
        ca,cb=aa.pop('classification'),bb.pop('classification')
        if aa!=bb:boxes.append(i)
        if any(ca[s]['screw']!=cb[s]['screw'] for s in ('reference','target')) or ca['action']!=cb['action']:
            decisions.append(i)
    ah={c['id']:c['input_hashes'] for c in base['candidate_timings']}
    bh={c['id']:c['input_hashes'] for c in new['candidate_timings']}
    input_changes=[i for i in ah if ah[i]!=bh[i]]
    def images(d):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(d['result_path']).parent.glob('*.png')}
    ai,bi=images(base),images(new)
    image_changes=sorted(k for k in set(ai)|set(bi) if ai.get(k)!=bi.get(k))
    result=dict(registration_or_audit_changes=changed,candidate_changes=boxes,decision_changes=decisions,
        dino_input_changes=input_changes,image_changes=image_changes,images=len(ai),candidates=len(ac))
    assert not any(result[k] for k in ('registration_or_audit_changes','candidate_changes','decision_changes','dino_input_changes','image_changes')),result
    return result


def main():
    OUT.mkdir(exist_ok=True)
    baseline=ROOT/'workspace/dino-folder-timing-20261104-072634-gpu-worker-prepared-once-fixed-shape/timing.json'
    warm=ROOT/'workspace/dino-folder-timing-20261104-072718-gpu-worker-prepared-once-fixed-shape-cpu-reuse-warm/timing.json'
    first=load(baseline)
    initial=[dict(mode='off',path=str(baseline)),dict(mode='warm',path=str(warm),verification=compare(first,load(warm)))]
    (OUT/'gpu-initial.json').write_text(json.dumps(initial,ensure_ascii=False,indent=2),encoding='utf-8')
    runs=[]
    preservation=protected()
    (OUT/'preservation-before.json').write_text(json.dumps(preservation,ensure_ascii=False,indent=2),encoding='utf-8')
    for i,mode in enumerate(['off','warm','warm','off','cold'],1):
        before=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))
        gpu_before=subprocess.check_output(['nvidia-smi','-q','-d','PERFORMANCE,POWER,TEMPERATURE,CLOCK']).decode(errors='replace')
        command=[sys.executable,str(ROOT/'experiments/dino/folder_pipeline_timing.py'),'--prepare-once','--cpu-reuse',mode]
        print(f'CPU run {i}/5: {mode}',flush=True)
        with (OUT/f'cpu-run-{i}.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode:raise RuntimeError((OUT/f'cpu-run-{i}.log').read_text(encoding='utf-8'))
        created=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))-before
        assert len(created)==1,created
        path=created.pop();data=load(path)
        proof=compare(first,data)
        gpu_after=subprocess.check_output(['nvidia-smi','-q','-d','PERFORMANCE,POWER,TEMPERATURE,CLOCK']).decode(errors='replace')
        (OUT/f'gpu-{i}.txt').write_text(gpu_before+'\nAFTER\n'+gpu_after,encoding='utf-8')
        runs.append(dict(mode=mode,path=str(path),verification=proof))
        (OUT/'runs.json').write_text(json.dumps(runs,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"Completed {mode}: total {data['total_seconds']:.3f}s, analysis {data['analysis_seconds']:.3f}s; all {proof['candidates']} candidates and {proof['images']} images unchanged",flush=True)
    after=protected();changes=[p for p,h in preservation.items() if after.get(p)!=h]
    assert not changes,changes
    (OUT/'preservation-after.json').write_text(json.dumps(dict(files=len(preservation),changes=changes),indent=2),encoding='utf-8')
    print('PASS: all timing runs and production preservation',flush=True)


if __name__=='__main__':main()
