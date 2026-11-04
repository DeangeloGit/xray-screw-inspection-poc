"""Sequential tests so CPU timing is not contaminated by other experiments."""
import sys,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.three_speed_runs import OUT,save,preservation
from experiments.dino.cpu_reuse_runs import compare

def main():
    jobs=[('交錯重測三項與合併','three_speed_runs.py',[]),
          ('原方法：取圖到DINO出結果','three_speed_full_pipeline.py',['base']),
          ('合併方法：取圖到DINO出結果','three_speed_full_pipeline.py',['combined']),
          ('既有59案例的來源影像核對','verify_three_speed.py',[]),
          ('既有59案例實際DINO複驗','verify_fast_runtime.py',['--cpu-inference','--output',str(OUT/'dino-cases')])]
    completed=[];full=[]
    for label,script,args in jobs:
        print('START '+label,flush=True);save('progress.json',dict(current=label,completed=completed))
        before=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))
        with (OUT/(script.replace('.py','')+'-'+str(len(completed))+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,str(ROOT/'experiments/dino'/script),*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'{script} failed: see log')
        if script=='three_speed_full_pipeline.py':
            created=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))-before
            assert len(created)==1
            p=created.pop();data=json.loads(p.read_text(encoding='utf-8'))
            full.append(dict(mode=args[0],path=str(p)))
            if len(full)==2:
                baseline=json.loads(Path(full[0]['path']).read_text(encoding='utf-8'))
                proof=compare(baseline,data);save('full-pipeline-verification.json',proof)
            save('full-pipeline-runs.json',full)
        completed.append(label);print('DONE '+label,flush=True)
    before=json.loads((OUT/'preservation-before.json').read_text(encoding='utf-8'));after=preservation()
    changed=[p for p,h in before.items() if after.get(p)!=h];assert not changed,changed
    save('preservation-after.json',dict(files=len(before),changes=changed))
    save('progress.json',dict(current='complete',completed=completed))
    print('PASS all timing, full-pipeline and fixed-case checks',flush=True)

if __name__=='__main__':main()
