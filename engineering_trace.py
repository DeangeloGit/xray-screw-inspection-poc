"""Opt-in image evidence and timings scoped to one engineering inspection."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

import cv2
import numpy as np

_active = ContextVar('engineering_trace', default=None)


@contextmanager
def capture(directory):
    record = {'directory': directory, 'images': {}, 'times': {}, 'onnx': {}, 'candidate': None}
    token = _active.set(record)
    try:
        yield record
    finally:
        _active.reset(token)


@contextmanager
def stage(name):
    record = _active.get()
    start = perf_counter() if record is not None else 0
    try:
        yield
    finally:
        if record is not None:
            record['times'][name] = record['times'].get(name, 0) + perf_counter() - start


def image(name, array, *, signed=False):
    record = _active.get()
    if record is None or name in record['images']:
        return
    if signed:
        intensity = np.clip(np.abs(array) / .30, 0, 1)
        array = np.stack((intensity * (array < 0), intensity * .32, intensity * (array > 0)), axis=-1)
    if array.dtype != np.uint8:
        array = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    filename = f'trace-{name}.png'
    ok, encoded = cv2.imencode('.png', array)
    if not ok:
        raise ValueError('無法保存工程中間圖')
    (record['directory'] / filename).write_bytes(encoded.tobytes())
    record['images'][name] = filename


@contextmanager
def candidate(number):
    record = _active.get()
    if record is None:
        yield
        return
    previous = record['candidate']
    record['candidate'] = number
    try:
        yield
    finally:
        record['candidate'] = previous


def enabled():
    return _active.get() is not None


def model_image(pil_image):
    record = _active.get()
    if record is None or record['candidate'] is None:
        return
    number = record['candidate']
    counts = record.setdefault('image_counts', {})
    counts[number] = counts.get(number, 0) + 1
    image(f'dino-{number}-{counts[number]:02d}', np.asarray(pil_image)[:, :, ::-1])


def inference(hit, seconds):
    record = _active.get()
    if record is not None:
        key = record['candidate']
        counts = record['onnx'].setdefault(key, {'runs': 0, 'hits': 0, 'seconds': 0})
        counts['hits' if hit else 'runs'] += 1
        counts['seconds'] += seconds
