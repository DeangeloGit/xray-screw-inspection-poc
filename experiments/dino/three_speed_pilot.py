"""Process-local experiments; preserve search coverage, formulas and result order."""
import inspect
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np


def brightness(ref, target):
    # Keep the original dtype promotion and operation order, including rounding.
    # Reuse scratch buffers; the last round's weights have no subsequent reader.
    weights = np.ones_like(ref, dtype=np.float32)
    wr, tmp, tmp2 = (np.empty_like(ref) for _ in range(3))
    def average(a):
        return cv2.boxFilter(a, -1, (101, 101), normalize=True, borderType=cv2.BORDER_REFLECT)
    for round_index in range(3):
        mass = average(weights); np.maximum(mass, .01, out=mass)
        np.multiply(weights, ref, out=wr)
        mean_ref = average(wr); np.divide(mean_ref, mass, out=mean_ref)
        np.multiply(weights, target, out=tmp)
        mean_target = average(tmp); np.divide(mean_target, mass, out=mean_target)
        np.multiply(wr, ref, out=tmp)
        variance = average(tmp); np.divide(variance, mass, out=variance)
        np.square(mean_ref, out=tmp); np.subtract(variance, tmp, out=variance)
        np.maximum(variance, 0, out=variance)
        np.multiply(wr, target, out=tmp)
        covariance = average(tmp); np.divide(covariance, mass, out=covariance)
        np.multiply(mean_ref, mean_target, out=tmp); np.subtract(covariance, tmp, out=covariance)
        # Short row strips keep consecutive arithmetic near one another in memory.
        predicted = np.empty_like(ref)
        if round_index == 0:
            # Input images can be float64; the original first reweight promotes
            # the initial float32 weights to the predicted image's dtype.
            weights = np.empty_like(predicted)
        for top in range(0, ref.shape[0], 64):
            sl = slice(top, top+64)
            a, b = tmp[sl], tmp2[sl]
            np.add(covariance[sl], .002, out=a); np.add(variance[sl], .002, out=b)
            np.divide(a,b,out=a); np.clip(a,.6,1.6,out=a)  # gain
            np.multiply(a,mean_ref[sl],out=b); np.subtract(mean_target[sl],b,out=b)
            np.clip(b,-.25,.25,out=b)  # offset
            np.multiply(a,ref[sl],out=a); np.add(a,b,out=predicted[sl])
            np.clip(predicted[sl],0,1,out=predicted[sl])
            if round_index < 2:
                np.subtract(predicted[sl],target[sl],out=a); np.abs(a,out=a)
                np.maximum(a,.0001,out=a); np.divide(.04,a,out=a)
                np.minimum(1,a,out=a); np.square(a,out=weights[sl])
    return predicted


class ThreeSpeed:
    def __init__(self, detector, reuse, mode, workers=2, inner_threads=1):
        self.d=detector; self.reuse=reuse; self.mode=mode; self.workers=workers
        self.old={}; self.pool=None; self.inner_threads=inner_threads

    def directions(self, raw, dr):
        def one(rotation):
            rotated=np.rot90(raw,rotation).copy()
            scale=1536/max(rotated.shape)
            target=cv2.resize(rotated,None,fx=scale,fy=scale)
            orb=cv2.ORB_create(nfeatures=7000)
            kt,dt=orb.detectAndCompute((target*255).astype('uint8'),None)
            pairs=None if dt is None or dr is None else cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(dt,dr,k=2)
            return target,scale,kt,dt,pairs
        # Global OpenCV thread count is changed only while this isolated stage runs.
        threads=cv2.getNumThreads(); cv2.setNumThreads(self.inner_threads)
        try:return list(self.pool.map(one,range(4)))
        finally:cv2.setNumThreads(threads)

    def candidate_map(self, ref, target, candidates, threshold):
        threads=cv2.getNumThreads(); cv2.setNumThreads(1)
        try:
            return list(self.pool.map(lambda c:self.d._three_check_one(ref,target,c,threshold),candidates))
        finally:cv2.setNumThreads(threads)

    def install(self):
        if self.mode=='base': return self
        self.old={k:getattr(self.d,k) for k in ('_register_orientation','compensate_brightness','proposals')}
        self.d._three_speed=self
        self.pool=ThreadPoolExecutor(max_workers=self.workers)
        if self.mode in ('align','combined'):
            source=inspect.getsource(self.reuse.original['_register_orientation'])
            source=source.replace("kr, dr = orb.detectAndCompute((ref * 255).astype('uint8'), None)",
                'kr, dr = _cpu_reuse.reference_features(orb, ref)\n    prepared_directions = _three_speed.directions(raw, dr)')
            first=source.index('        rotated = '); last=source.index('        good = ',first)
            source=source[:first]+'''        target, s, kt, dt, pairs = prepared_directions[rotation]
        if pairs is None:
            continue
'''+source[last:]
            exec(compile(source,'<three-speed-align>','exec'),self.d.__dict__)
        if self.mode in ('brightness','combined'): self.d.compensate_brightness=brightness
        if self.mode in ('candidates','combined'):
            source=inspect.getsource(self.reuse.original['proposals'])
            start=source.index('    retained = []\n'); end=source.index('    retained.sort(',start)
            loop=source[source.index('        evidence = ',start):end]
            # Extract exactly the existing per-candidate decision chain.
            loop=loop.replace("        if explained:\n            if structure_changes is not None:\n                structure_changes.append(c)\n        else:","        if not explained:")
            loop=loop.replace('            retained.append(c)\n','')
            helper='def _three_check_one(ref, target, c, threshold):\n'+''.join(line[4:]+'\n' for line in loop.splitlines())+'    return c, explained\n'
            exec(compile(helper,'<three-speed-candidate>','exec'),self.d.__dict__)
            replacement='''    retained = []
    for c, explained in _three_speed.candidate_map(ref, target, candidates, threshold):
        if explained:
            if structure_changes is not None:
                structure_changes.append(c)
        else:
            retained.append(c)
'''
            exec(compile(source[:start]+replacement+source[end:],'<three-speed-proposals>','exec'),self.d.__dict__)
            fn=self.d.proposals
            def local_arrays(*args,**kwargs):
                self.reuse.shared=None
                try:return fn(*args,**kwargs)
                finally:self.reuse.shared=None
            self.d.proposals=local_arrays
        return self

    def uninstall(self):
        for k,v in self.old.items():setattr(self.d,k,v)
        if self.pool:self.pool.shutdown(wait=True)
        for k in ('_three_speed','_three_check_one'):self.d.__dict__.pop(k,None)
