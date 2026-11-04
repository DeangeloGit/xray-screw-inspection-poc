"""Experiment-only reuse of immutable reference data and per-photo scratch arrays.

Installs into this process only; no production modules or detector rules are edited.
"""
import hashlib
import inspect
from pathlib import Path
import time

import cv2
import numpy as np


class CpuReuse:
    def __init__(self, detector, reference):
        self.d = detector
        self.path = Path(reference).resolve()
        self.original = {name: getattr(detector, name) for name in
            ('read', 'structure_mask', 'machine_mask', '_register_orientation', 'candidates_from_residual', 'proposals', 'detect')}
        self.key = self.full = self.small = self.structure = self.machine = self.features = None
        self.shared = None
        self.stats = dict(reference_builds=0, reference_prepare_seconds=0., reference_hits=0,
                          feature_hits=0, structure_hits=0, machine_hits=0,
                          shared_builds=0, shared_hits=0, zero_flow_builds=0)

    def prepare_reference(self):
        # Content hash also invalidates a file replaced with identical size/timestamp.
        payload = self.path.read_bytes()
        key = (str(self.path), hashlib.sha256(payload).hexdigest())
        if key == self.key:
            self.stats['reference_hits'] += 1
            return self.full
        start = time.perf_counter()
        self.key = None
        full = self.original['read'](self.path)
        small = cv2.resize(full, None, fx=1536/max(full.shape), fy=1536/max(full.shape))
        structure = self.original['structure_mask'](small)
        machine = self.original['machine_mask'](small)
        cv2.setRNGSeed(7)
        features = cv2.ORB_create(nfeatures=7000).detectAndCompute((small*255).astype('uint8'), None)
        if self.path.read_bytes() != payload:
            raise ValueError('參照圖於準備期間變更，請重試')
        self.full, self.small = full, small
        self.structure, self.machine, self.features = structure, machine, features
        self.key = key
        for array in (full, small, structure, machine):
            array.flags.writeable = False
        self.stats['reference_builds'] += 1
        self.stats['reference_prepare_seconds'] += time.perf_counter()-start
        return self.full

    def read(self, path):
        return self.prepare_reference() if Path(path).resolve() == self.path else self.original['read'](path)

    def reference_small(self, full):
        assert full is self.full
        return self.small

    def structure_mask(self, ref):
        if self.key is not None and ref is self.small:
            self.stats['structure_hits'] += 1
            return self.structure
        return self.original['structure_mask'](ref)

    def machine_mask(self, ref):
        if self.key is not None and ref is self.small:
            self.stats['machine_hits'] += 1
            return self.machine
        return self.original['machine_mask'](ref)

    def reference_features(self, orb, ref):
        if self.key is not None and ref is self.small:
            self.stats['feature_hits'] += 1
            return self.features
        return orb.detectAndCompute((ref*255).astype('uint8'), None)

    def candidate_arrays(self, predicted, target):
        if self.shared is None or self.shared[0] is not predicted or self.shared[1] is not target:
            nearby = cv2.erode(predicted, np.ones((15,15), np.uint8))
            difference = predicted-target
            self.shared = (predicted, target, nearby, difference)
            self.stats['shared_builds'] += 1
        else:
            self.stats['shared_hits'] += 1
        return self.shared[2:]

    def zero_flow(self, flow):
        self.stats['zero_flow_builds'] += 1
        return np.zeros_like(flow)

    def _replace(self, name, replacements):
        source = inspect.getsource(self.original[name])
        for old, new in replacements:
            assert source.count(old) == 1, (name, old)
            source = source.replace(old, new)
        exec(compile(source, f'<cpu-reuse-experiment:{name}>', 'exec'), self.d.__dict__)

    def install(self):
        self.d._cpu_reuse = self
        self.d.read = self.read
        self.d.structure_mask = self.structure_mask
        self.d.machine_mask = self.machine_mask
        self._replace('_register_orientation', [
            ("kr, dr = orb.detectAndCompute((ref * 255).astype('uint8'), None)",
             'kr, dr = _cpu_reuse.reference_features(orb, ref)')])
        self._replace('candidates_from_residual', [
            ('normal_nearby = cv2.erode(predicted, np.ones((15, 15), np.uint8))\n    signed_difference = predicted - target',
             'normal_nearby, signed_difference = _cpu_reuse.candidate_arrays(predicted, target)')])
        self._replace('detect', [
            ('r = cv2.resize(ref, None, fx=1536/max(ref.shape), fy=1536/max(ref.shape))',
             'r = _cpu_reuse.reference_small(ref)'),
            ('for i, c in enumerate(baseline, 1):',
             'zero_flow = _cpu_reuse.zero_flow(flow)\n    for i, c in enumerate(baseline, 1):'),
            ("reg, np.zeros_like(flow), raw.shape)", 'reg, zero_flow, raw.shape)')])
        proposals = self.original['proposals']
        def with_local_arrays(*args, **kwargs):
            self.shared = None
            try:
                return proposals(*args, **kwargs)
            finally:
                self.shared = None
        self.d.proposals = with_local_arrays
        return self

    def uninstall(self):
        for name, function in self.original.items():
            setattr(self.d, name, function)
        self.shared = None
        self.d.__dict__.pop('_cpu_reuse', None)
