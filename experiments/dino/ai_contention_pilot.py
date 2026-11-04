"""Balanced three-way causal probe, same full photo and actual CPU DINO."""
import sys,json,subprocess,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-ai-contention-20261104'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(n,d):OUT.mkdir(exist_ok=True);(OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def worker(mode):
    from experiments.dino.ai_thread_audit import Audit
    audit=Audit(mode);original=ROOT/'experiments/dino/folder_pipeline_timing.py';s=original.read_text(encoding='utf-8')
    def replace(a,b):
        nonlocal s
        assert s.count(a)==1,a;s=s.replace(a,b)
    replace(" assert session.get_providers()[0]==provider,session.get_providers()", " _audit.ort_ready()\n assert session.get_providers()[0]==provider,session.get_providers()")
    key=" for name in ['read','register','refine','proposals','legacy_proposals','write_image']:"
    replace(key,f" from experiments.dino.three_speed_pilot import ThreeSpeed\n pilot=ThreeSpeed(detector,reuse,{'base' if mode=='base' else 'combined'!r},workers=2,inner_threads=16).install()\n"+key)
    replace(' def experiment(snapshot,target,reference,c):\n  current_inputs.clear()', ' def experiment(snapshot,target,reference,c):\n  _audit.begin(pilot)\n  current_inputs.clear()')
    replace('input_hashes=dict(current_inputs)))','input_hashes=dict(current_inputs),completed_at=time.perf_counter()))')
    replace(" if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse"," if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse\n mode+='-contention-"+mode+"'")
    replace(" (OUT/'timing.json').write_text("," output['thread_audit']=_audit.finish()\n output['start_to_dino_answer_seconds']=max(c['completed_at'] for c in candidates)-origin-output['folder_to_analysis_seconds']\n"+" (OUT/'timing.json').write_text(")
    sys.argv=[str(original),'--prepare-once','--cpu-reuse','warm']
    exec(compile(s,str(original),'exec'),dict(__name__='__main__',__file__=str(original),_audit=audit))
def main():
    from experiments.dino.three_speed_runs import preservation
    from experiments.dino.cpu_reuse_runs import compare
    before=preservation();save('preservation-before.json',before);rows=[];base=None
    for i,mode in enumerate(['base','combined','closed','closed','combined','base'],1):
        print(f'START {i}/6 {mode}',flush=True);save('progress.json',dict(run=i,mode=mode))
        old=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))
        with (OUT/f'{i}-{mode}.log').open('w',encoding='utf-8') as f:
            p=subprocess.run([sys.executable,__file__,'--worker',mode],stdout=f,stderr=subprocess.STDOUT,cwd=ROOT,timeout=300)
        assert p.returncode==0,f'See {i}-{mode}.log'
        added=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))-old;assert len(added)==1
        path=added.pop();d=load(path)
        if base is None:base=d
        proof=compare(base,d)
        row=dict(run=i,mode=mode,path=str(path),ai=d['detector_stage_seconds']['ai_total'],answer=d['start_to_dino_answer_seconds'],audit=d['thread_audit'],verification=proof)
        rows.append(row);save('runs.json',rows)
        print(f'DONE {i}/6 {mode}: AI={row["ai"]:.2f}s; answer={row["answer"]:.2f}s; poolCPU={row["audit"]["groups"]["python_pool"]["cpu_seconds"]:.4f}s; otherCPU={row["audit"]["groups"]["other_threads"]["cpu_seconds"]:.4f}s',flush=True)
    after=preservation();changes=[p for p,h in before.items() if after.get(p)!=h];assert not changes
    save('preservation-after.json',dict(files=len(before),changes=changes));save('progress.json',dict(status='complete'))
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(sys.argv[2])
    else:main()
