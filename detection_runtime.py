"""Bounded reference cache and deterministic per-stage parallel work."""
import contextlib
import contextvars
import hashlib
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

PIPELINE = 'dino-combined-20261104-r3'
LOCK = threading.RLock()
CURRENT = contextvars.ContextVar('detection_context', default=None)
_REFERENCES = OrderedDict()


class Reference:
    def __init__(self, path, payload, read, structure_mask, machine_mask):
        self.full = read(path)
        self.small = cv2.resize(self.full, None, fx=1536/max(self.full.shape), fy=1536/max(self.full.shape))
        self.structure = structure_mask(self.small)
        self.machine = machine_mask(self.small)
        cv2.setRNGSeed(7)
        self.features = cv2.ORB_create(nfeatures=7000).detectAndCompute((self.small*255).astype('uint8'), None)
        if Path(path).read_bytes() != payload:
            raise ValueError('參照圖於準備期間變更，請重試')
        for a in (self.full,self.small,self.structure,self.machine):
            a.flags.writeable = False


def prepare_reference(path, read, structure_mask, machine_mask):
    with LOCK:
        path = Path(path).resolve()
        payload = path.read_bytes()
        key = (str(path),hashlib.sha256(payload).hexdigest())
        if key not in _REFERENCES:
            _REFERENCES[key] = Reference(path,payload,read,structure_mask,machine_mask)
        _REFERENCES.move_to_end(key)
        while len(_REFERENCES)>2:
            _REFERENCES.popitem(last=False)
        return _REFERENCES[key]


class Context:
    def __init__(self, reference):
        self.reference = reference
        self.pair = None
        self.quantized = None

    def arrays(self, reference, target):
        if self.pair is None or self.pair[0] is not reference or self.pair[1] is not target:
            self.pair = (reference,target)
            self.quantized = [(np.clip(im,0,1)*255).astype('uint8').astype('float32')/255 for im in self.pair]
        return self.quantized


@contextlib.contextmanager
def detection(path, read, structure_mask, machine_mask):
    # OpenCV's thread count and RNG are process globals. Serialize full detection
    # calls while stage workers do independent calculations and ordered collection.
    with LOCK:
        reference = prepare_reference(path,read,structure_mask,machine_mask)
        token = CURRENT.set(Context(reference))
        try:
            yield CURRENT.get()
        finally:
            CURRENT.reset(token)


def parallel_map(fn, values, inner_threads):
    with LOCK:
        threads = cv2.getNumThreads()
        cv2.setNumThreads(inner_threads)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(fn,values))
        finally:
            cv2.setNumThreads(threads)


def directions(raw, descriptors):
    def one(rotation):
        rotated=np.rot90(raw,rotation).copy()
        scale=1536/max(rotated.shape)
        target=cv2.resize(rotated,None,fx=scale,fy=scale)
        kt,dt=cv2.ORB_create(nfeatures=7000).detectAndCompute((target*255).astype('uint8'),None)
        pairs=None if dt is None or descriptors is None else cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(dt,descriptors,k=2)
        return target,scale,kt,dt,pairs
    return parallel_map(one,range(4),16)
