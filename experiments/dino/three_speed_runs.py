"""Same-photo separate/combined timing and exact output comparison."""
import sys,json,time,hashlib,statistics,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import cv2
import detector
from experiments.dino.cpu_reuse_pilot import CpuReuse
from experiments.dino.cpu_reuse_runs import protected
from experiments.dino.alignment_difference_profile import measure,serialize
from experiments.dino.three_speed_pilot import ThreeSpeed
OUT=ROOT/'workspace/dino-three-speed-20261104'
REFERENCE=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/OK/cnd64409dv.tiff')
TARGET=Path('C:/Users/Deangelo_Hu/Pictures/X-Ray/MPT12/NG/CND6440DTD_2026_11_03_09_57_57_32.tiff')
def save(name,obj):
    OUT.mkdir(exist_ok=True);(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:x.item()),encoding='utf-8')
def preservation():
    result=protected()
    result.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (REFERENCE,TARGET)})
    return result
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--workers',type=int,default=2);parser.add_argument('--inner-threads',type=int,default=16);args=parser.parse_args()
    if not (OUT/'preservation-before.json').exists():save('preservation-before.json',preservation())
    reuse=CpuReuse(detector,REFERENCE).install();reuse.prepare_reference();raw=detector.read(TARGET)
    old=json.loads((ROOT/'workspace/dino-alignment-difference-profile-20261104/profile.json').read_text(encoding='utf-8'))['output_signature']
    configurations=[('base',2,16),('align',2,8),('align',4,4),('align',2,16),('align',4,16),('brightness',2,16),('candidates',2,1),('candidates',4,1)] if args.smoke else [(m,args.workers,args.inner_threads) for m in ['base','align','brightness','candidates','combined','combined','candidates','brightness','align','base','brightness','base','combined','align','candidates']]
    rows=[]
    try:
        for i,(mode,workers,inner_threads) in enumerate(configurations,1):
            pilot=ThreeSpeed(detector,reuse,mode,workers,inner_threads).install()
            try:stages,signature=measure(reuse.small,raw)
            finally:pilot.uninstall()
            changes=[k for k in old if serialize(signature[k])!=serialize(old[k])]
            row=dict(run=i,mode=mode,workers=workers,inner_threads=inner_threads,stages=stages,changed_fields=changes)
            rows.append(row);save('smoke.json' if args.smoke else 'timings.json',rows)
            print(f'{i}/{len(configurations)} {mode}/{workers}/{inner_threads}: {stages}; changes={changes}',flush=True)
            if changes:
                save(f'failure-{mode}-{workers}.json',signature)
                raise AssertionError(changes)
    finally:reuse.uninstall()
    before=json.loads((OUT/'preservation-before.json').read_text(encoding='utf-8'));after=preservation()
    changed=[p for p,h in before.items() if after.get(p)!=h]
    save('preservation-after.json',dict(files=len(before),changes=changed));assert not changed
if __name__=='__main__':main()
