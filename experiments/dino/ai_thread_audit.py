"""Read Windows per-thread CPU time; no process settings are changed."""
import ctypes as c
from ctypes import wintypes as w
import os,time
k=c.WinDLL('kernel32',use_last_error=True)
class Entry(c.Structure):
    _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('th32ThreadID',w.DWORD),('th32OwnerProcessID',w.DWORD),('tpBasePri',w.LONG),('tpDeltaPri',w.LONG),('dwFlags',w.DWORD)]
k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
k.Thread32First.argtypes=[w.HANDLE,c.POINTER(Entry)];k.Thread32Next.argtypes=k.Thread32First.argtypes
k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenThread.restype=w.HANDLE
k.GetThreadTimes.argtypes=[w.HANDLE,*([c.POINTER(w.FILETIME)]*4)]
k.CloseHandle.argtypes=[w.HANDLE]
def ticks(t):return (t.dwHighDateTime<<32)+t.dwLowDateTime
def threads():
    snap=k.CreateToolhelp32Snapshot(4,0);entry=Entry();entry.dwSize=c.sizeof(entry);result={}
    try:
        more=k.Thread32First(snap,c.byref(entry))
        while more:
            if entry.th32OwnerProcessID==os.getpid():
                h=k.OpenThread(0x0800,False,entry.th32ThreadID)
                if h:
                    ts=[w.FILETIME() for _ in range(4)]
                    try:
                        if k.GetThreadTimes(h,*[c.byref(t) for t in ts]):result[entry.th32ThreadID]=(ticks(ts[2])+ticks(ts[3]))/1e7
                    finally:k.CloseHandle(h)
            more=k.Thread32Next(snap,c.byref(entry))
    finally:k.CloseHandle(snap)
    return result
def system():
    ts=[w.FILETIME() for _ in range(3)];assert k.GetSystemTimes(*[c.byref(t) for t in ts])
    return (ticks(ts[1])+ticks(ts[2])-ticks(ts[0]))/1e7

class Audit:
    def __init__(self,mode):self.mode=mode;self.started=False;self.before_ort=threads();self.ort_ids=set()
    def ort_ready(self):self.ort_ids=set(threads())-set(self.before_ort)
    def begin(self,pilot):
        if self.started:return
        self.started=True;pool=pilot.pool
        self.pool_ids=[t.native_id for t in pool._threads] if pool else []
        t=time.perf_counter()
        if self.mode=='closed' and pool:pool.shutdown(wait=True)
        self.shutdown_seconds=time.perf_counter()-t
        self.start_threads=threads();self.start_cpu=time.process_time();self.start_system=system();self.start=time.perf_counter()
    def finish(self):
        wall=time.perf_counter()-self.start;end=threads();process=time.process_time()-self.start_cpu
        deltas={i:v-self.start_threads.get(i,0.) for i,v in end.items()}
        groups={'main': [__import__('threading').main_thread().native_id],'ort_workers':list(self.ort_ids),'python_pool':self.pool_ids}
        known=set(sum(groups.values(),[]));groups['other_threads']=[i for i in deltas if i not in known]
        return dict(wall_seconds=wall,process_cpu_seconds=process,system_busy_core_seconds=system()-self.start_system,
            external_busy_core_seconds=max(0,system()-self.start_system-process),logical_cpus=os.cpu_count(),
            groups={name:dict(ids=ids,cpu_seconds=sum(deltas.get(i,0) for i in ids)) for name,ids in groups.items()},
            start_thread_count=len(self.start_threads),end_thread_count=len(end),closed_pool=self.mode=='closed',
            pool_threads_alive_at_ai_start=[i for i in self.pool_ids if i in self.start_threads],shutdown_seconds=self.shutdown_seconds,
            new_thread_ids=[i for i in end if i not in self.start_threads])
