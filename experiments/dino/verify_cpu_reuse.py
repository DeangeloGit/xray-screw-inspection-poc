"""Check all source pairs represented by the existing59 screw/normal cases."""
import sys
import json
import hashlib
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import cv2
from PIL import Image
import detector
from experiments.dino.cpu_reuse_pilot import CpuReuse

OUT=ROOT/'workspace/dino-cpu-reuse-20261104'


def same(a,b):
    def encode(x):
        return json.dumps(x,sort_keys=True,default=lambda v:v.item())
    return encode(a)==encode(b)


def main():
    OUT.mkdir(exist_ok=True)
    cases=json.loads((ROOT/'workspace/dino-learn-joint-20261103/results.json').read_text(encoding='utf-8'))
    sources=list(dict.fromkeys(z['source'] for z in cases))
    results=[]
    for number,source in enumerate(sources,1):
        path=Path(source)/'reference.png'
        normal=detector.read(path)
        small=cv2.resize(normal,None,fx=1536/max(normal.shape),fy=1536/max(normal.shape))
        mask_expected=detector.machine_mask(small)
        structure_expected=detector.structure_mask(small)
        cv2.setRNGSeed(7)
        kp,des=cv2.ORB_create(nfeatures=7000).detectAndCompute((small*255).astype('uint8'),None)
        # Frozen aligned arrays retain their original pixels; no new registration or label selection.
        ref,tar=[np.asarray(Image.open(Path(source)/f).convert('L'),np.float32)/255 for f in ('reference.png','aligned.png')]
        mask=detector.machine_mask(ref)
        before_changes=[]
        before,residual=detector.proposals(ref,tar,mask,.13,before_changes)
        reuse=CpuReuse(detector,path).install()
        try:
            cached=reuse.prepare_reference()
            assert np.array_equal(cached,normal)
            assert np.array_equal(reuse.small,small)
            assert np.array_equal(detector.machine_mask(reuse.small),mask_expected)
            assert np.array_equal(detector.structure_mask(reuse.small),structure_expected)
            assert np.array_equal(reuse.features[1],des)
            assert [(p.pt,p.angle,p.response,p.octave) for p in reuse.features[0]]==[(p.pt,p.angle,p.response,p.octave) for p in kp]
            assert reuse.read(path) is cached and reuse.stats['reference_builds']==1
            after_changes=[]
            after,new_residual=detector.proposals(ref,tar,mask,.13,after_changes)
            assert same(before,after) and same(before_changes,after_changes),source
            assert np.array_equal(residual,new_residual),source
            assert reuse.stats['shared_builds']==1 and reuse.stats['shared_hits']==1
            # Zero flow reused for all audit candidates must map positions identically.
            assert np.array_equal(reuse.zero_flow(np.zeros((*ref.shape,2),np.float32)),np.zeros((*ref.shape,2),np.float32))
            results.append(dict(source=source,cases=[z['number'] for z in cases if z['source']==source],
                candidates=len(before),structure_changes=len(before_changes),candidate_changes=0,
                reference_pixels_identical=True,reference_features_identical=True,residual_identical=True))
        finally:
            reuse.uninstall()
        print(f'PASS source {number}/{len(sources)}; candidates {len(before)}, cases {results[-1]["cases"]}',flush=True)
    # A changed reference must invalidate even when file size and modification time are unchanged.
    with tempfile.TemporaryDirectory(prefix='xray-reference-cache-') as temp:
        import os
        path=Path(temp)/'ref.bmp'
        rng=np.random.default_rng(11)
        a=rng.integers(0,256,(160,160),dtype=np.uint8)
        Image.fromarray(a).save(path)
        reuse=CpuReuse(detector,path).install()
        try:
            first=reuse.prepare_reference().copy();stat=path.stat()
            Image.fromarray(np.flipud(a)).save(path)
            os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            second=reuse.prepare_reference()
            assert path.stat().st_size==stat.st_size
            assert not np.array_equal(first,second) and reuse.stats['reference_builds']==2
        finally:
            reuse.uninstall()
    result=dict(sources=len(sources),cases=len(cases),candidate_changes=0,
        reference_features_identical=True,changed_reference_invalidates=True,results=results)
    (OUT/'upstream-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: reference cache + candidate extraction, all existing case sources',flush=True)


if __name__=='__main__':main()
