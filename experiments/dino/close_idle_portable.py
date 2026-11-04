"""Close the specifically authorized portable only in a verified idle retry gap."""
import ctypes as c,json,sqlite3,time,hashlib
from ctypes import wintypes as w
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-after-portable-close-20261104';OUT.mkdir(exist_ok=True)
USER=Path('C:/Users/Deangelo_Hu/AppData/Local/XRayReview')
EXE=USER/'versions/cpu-7de80f4925b7e0c5/XRayReview-Windows-x64-CPU/runtime/python.exe'
DB=USER/'workspace/state/acquisition.sqlite3'
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
k.GetProcessTimes.argtypes=[w.HANDLE,*([c.POINTER(w.FILETIME)]*4)]
k.TerminateProcess.argtypes=[w.HANDLE,w.UINT];k.CloseHandle.argtypes=[w.HANDLE]
def states():
    with sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True) as db:
        return dict(db.execute('select state,count(*) from events group by state'))
def cpu(h):
    ts=[w.FILETIME() for _ in range(4)];assert k.GetProcessTimes(h,*[c.byref(t) for t in ts])
    return sum((ts[i].dwHighDateTime<<32)+ts[i].dwLowDateTime for i in (2,3))/1e7
def main():
    preserved={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [USER/'config/station.json',USER/'workspace/state/ui_settings.json']}
    h=k.OpenProcess(0x1001,False,3244);assert h,'Target not accessible'
    name=c.create_unicode_buffer(32768);n=w.DWORD(len(name));assert k.QueryFullProcessImageNameW(h,0,name,c.byref(n))
    assert Path(name.value).resolve()==EXE.resolve(),name.value
    rows=[];idle=0;start=time.perf_counter();previous=cpu(h)
    try:
        while time.perf_counter()-start<90:
            time.sleep(.2);now=cpu(h);s=states();delta=now-previous;previous=now
            row=dict(elapsed=time.perf_counter()-start,states=s,cpu_delta=delta);rows.append(row)
            eligible=s.get('analyzing',0)==0 and s.get('pending',0)==0 and s.get('analysis_error',0)==1 and delta<=.016
            idle=idle+1 if eligible else 0
            if idle>=3:
                # Recheck immediately before the authorized stop, inside the same gap.
                final=states();assert final.get('analyzing',0)==0 and final.get('pending',0)==0
                assert k.TerminateProcess(h,0),c.get_last_error()
                evidence=dict(pid=3244,executable=name.value,closed=True,reason='No analyzing/pending entries and three low-CPU samples in the retry wait gap',samples=rows,final_states=final,preserved_files=preserved)
                (OUT/'portable-close-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
                assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in preserved.items())
                print('Closed authorized portable at idle gap; final states:',final,flush=True);return
        (OUT/'portable-close-evidence.json').write_text(json.dumps(dict(closed=False,samples=rows),ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('No verified idle gap; process left running')
    finally:k.CloseHandle(h)
if __name__=='__main__':main()
