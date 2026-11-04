"""Existing screw/wire/board case sources only, no new dataset-wide detection."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
import detector
from experiments.dino.cpu_reuse_pilot import CpuReuse
from experiments.dino.three_speed_pilot import ThreeSpeed,brightness
from experiments.dino.three_speed_runs import OUT,REFERENCE,save,preservation
from experiments.dino.alignment_difference_profile import serialize

def main():
    cases=json.loads((ROOT/'workspace/dino-learn-joint-20261103/results.json').read_text(encoding='utf-8'))
    sources=list(dict.fromkeys(z['source'] for z in cases));rows=[]
    reuse=CpuReuse(detector,REFERENCE).install()
    try:
        for number,source in enumerate(sources,1):
            paths=[Path(source)/f for f in ('reference.png','aligned.png')]
            hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            ref,tar=[np.asarray(Image.open(p).convert('L'),np.float32)/255 for p in paths]
            expected=detector.compensate_brightness(ref,tar);actual=brightness(ref,tar)
            assert expected.tobytes()==actual.tobytes(),('brightness',source)
            mask=detector.machine_mask(ref);bc=[];ac=[]
            before,residual=detector.proposals(ref,tar,mask,.13,bc)
            pilot=ThreeSpeed(detector,reuse,'combined',workers=2,inner_threads=16).install()
            try:after,new=detector.proposals(ref,tar,mask,.13,ac)
            finally:pilot.uninstall()
            assert serialize(before)==serialize(after) and serialize(bc)==serialize(ac),('candidates',source)
            assert residual.tobytes()==new.tobytes(),('residual',source)
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in hashes.items())
            rows.append(dict(source=source,cases=[z['number'] for z in cases if z['source']==source],candidates=len(before),structure_changes=len(bc),candidate_changes=0,residual_identical=True,brightness_identical=True,source_hashes=hashes))
            save('case-source-verification.json',dict(sources=len(rows),expected_sources=len(sources),cases=len(cases),results=rows))
            print(f'PASS {number}/{len(sources)} sources; candidates={len(before)}; cases={rows[-1]["cases"]}',flush=True)
    finally:reuse.uninstall()
    before=json.loads((OUT/'preservation-before.json').read_text(encoding='utf-8'));after=preservation()
    changed=[p for p,h in before.items() if after.get(p)!=h]
    save('preservation-after.json',dict(files=len(before),changes=changed));assert not changed

if __name__=='__main__':main()
