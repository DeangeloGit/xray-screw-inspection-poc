"""GPU counterpart of the eight-run CPU protocol; reject constrained GPU runs."""
import sys,json,subprocess,time,threading,inspect,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-gpu-paired-timing-20261104';OUT.mkdir(exist_ok=True)
def save(n,d):(OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def state():
    g=ET.fromstring(subprocess.check_output(['nvidia-smi','-q','-x'],creationflags=subprocess.CREATE_NO_WINDOW)).find('gpu')
    def value(path):return g.findtext(path)
    return dict(wall=time.time(),monotonic=time.perf_counter(),name=value('product_name'),pstate=value('performance_state'),
        sm=value('clocks/sm_clock'),memory=value('clocks/mem_clock'),utilization=value('utilization/gpu_util'),
        temperature=value('temperature/gpu_temp'),draw=value('gpu_power_readings/instant_power_draw'),
        current_limit=value('gpu_power_readings/current_power_limit'),requested_limit=value('gpu_power_readings/requested_power_limit'),
        sw_thermal=value('clocks_event_reasons/clocks_event_reason_sw_thermal_slowdown'),
        sw_power=value('clocks_event_reasons/clocks_event_reason_sw_power_cap'),
        hw_slowdown=value('clocks_event_reasons/clocks_event_reason_hw_slowdown'))
def constrained(s):
    try:return s['sw_thermal']=='Active' or s['hw_slowdown']=='Active' or float(s['current_limit'].split()[0])<float(s['requested_limit'].split()[0])*.9
    except Exception:return True
class Monitor:
    def __init__(self):self.rows=[];self.stop=threading.Event()
    def run(self):
        while not self.stop.is_set():
            try:self.rows.append(state())
            except Exception as e:self.rows.append(dict(error=str(e),monotonic=time.perf_counter()))
            self.stop.wait(.5)
    def __enter__(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join(timeout=10)
def worker(mode):
    from experiments.dino import paired_answer_timing as cpu
    source=inspect.getsource(cpu.worker).replace('def worker(mode):','def gpu_worker(mode):')
    old="sys.argv=[str(original),'--prepare-once','--cpu-reuse','warm']"
    assert source.count(old)==1
    source=source.replace(old,"sys.argv=[str(original),'--prepare-once','--cpu-reuse','warm','--gpu','--gpu-api','worker','--fixed-shape']")
    scope=dict(cpu.__dict__);exec(compile(source,'<gpu-paired-worker>','exec'),scope);scope['gpu_worker'](mode)
def probe():
    import numpy as np
    from PIL import Image
    from gpu_runtime import GpuSession
    model=ROOT/'models/dino-paired-47-20261103';m=load(model/'manifest.json')
    bank=np.load(ROOT/'workspace/dino-contrast-pair-20261103/bank-features.npz')['bank'];labels=np.r_[np.ones(47,bool),np.zeros(65,bool)]
    expected=load(ROOT/'workspace/dino-four-remaining-20261103/restricted-results.json')[0]
    session=None;rows=[]
    with Monitor() as monitor:
        try:
            session=GpuSession(model/'model.onnx',m['sha256'])
            for side in ['reference','target']:
                import hashlib
                im=Image.open(ROOT/f'workspace/dino-four-remaining-20261103/images/1-final-{side}.png').convert('RGB')
                assert hashlib.sha256(im.tobytes()).hexdigest()==expected['input_hashes'][side]
                a=np.asarray(im,np.float32)/255;a=(a-np.asarray(m['mean'],np.float32))/np.asarray(m['std'],np.float32)
                begin=time.perf_counter();raw=session.run(None,{session.get_inputs()[0].name:a.transpose(2,0,1)[None]})[0][0];elapsed=time.perf_counter()-begin
                v=np.stack([raw[0],raw[1:].mean(axis=0)]);v/=np.linalg.norm(v,axis=1)[:,None]
                scores=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
                margin=sum(float(np.sort(s[labels])[-3:].mean()-np.sort(s[~labels])[-3:].mean()) for s in scores)/2
                row=dict(side=side,seconds=elapsed,screw=margin>=0,margin=margin,expected=expected['new'][side]['screw'])
                assert row['screw']==row['expected'];rows.append(row)
            result=dict(device=session.device,providers=session.get_providers(),rows=rows,decision_changes=0)
        finally:
            if session:session.close()
    result['samples']=monitor.rows;result['constrained_samples']=sum(constrained(s) for s in monitor.rows)
    save('short-probe.json',result);print('Short real-input probe',json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)
def main():
    from experiments.dino.three_speed_runs import preservation
    from experiments.dino.cpu_reuse_runs import compare
    before=preservation();save('preservation-before.json',before)
    samples=[];valid=[];baseline=None
    try:
        # Bounded readiness checks; no power, clock, driver or application changes.
        for i in range(7):
            s=state();samples.append(s);save('preflight.json',samples)
            print(f'GPU readiness {i+1}/7: {s["sm"]}, {s["current_limit"]}, thermal={s["sw_thermal"]}',flush=True)
            if not constrained(s):break
            if i==0:probe()
            if i<6:time.sleep(20)
        if constrained(samples[-1]):
            save('status.json',dict(status='not_ready',reason='GPU power/thermal constraint persisted; no valid full-photo paired run',completed_pairs=0));return
        for i,mode in enumerate(['base','combined','combined','base','combined','base','base','combined'],1):
            if constrained(state()):raise RuntimeError('GPU became constrained before run')
            old=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))
            with Monitor() as monitor:
                with (OUT/f'run-{i}-{mode}.log').open('w',encoding='utf-8') as log:
                    p=subprocess.run([sys.executable,__file__,'--worker',mode],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            save(f'gpu-samples-{i}.json',monitor.rows);assert p.returncode==0
            added=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))-old;assert len(added)==1
            path=added.pop();d=load(path)
            if baseline is None:baseline=d
            proof=compare(baseline,d)
            prior=load(ROOT/'workspace/dino-after-portable-close-20261104/runs.json')[0]
            cpu_proof=compare(load(prior['path']),d)
            intervals=[(c['completed_at']-c['seconds'],c['completed_at']) for c in d['candidate_timings']]
            active=[s for s in monitor.rows if any(a<=s.get('monotonic',0)<=b for a,b in intervals)]
            assert active,'No telemetry covering DINO'
            bad=[s for s in active if constrained(s)]
            valid.append(dict(run=i,mode=mode,path=str(path),gpu_samples=len(active),limited_samples=len(bad),verification=proof,cpu_verification=cpu_proof))
            save('runs.json',valid)
            if bad:raise RuntimeError('GPU constrained during AI; run invalid for normal-speed comparison')
            print(f'DONE GPU {i}/8 {mode}: {d["start_to_dino_answer_seconds"]:.2f}s; unchanged, GPU verified',flush=True)
        save('status.json',dict(status='complete',runs=8))
    finally:
        after=preservation();changes=[p for p,h in before.items() if after.get(p)!=h]
        save('preservation-after.json',dict(files=len(before),changes=changes));assert not changes
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(sys.argv[2])
    else:main()
