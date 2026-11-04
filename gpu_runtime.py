"""ORT-compatible local worker client. Explicit GPU errors never masquerade as CPU."""
import atexit
import queue
import subprocess
import threading
import weakref
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from gpu_protocol import receive, send
from runtime_paths import INSTALL_ROOT, RESOURCE_ROOT

_sessions = weakref.WeakSet()


def runtime_python():
    for path in (INSTALL_ROOT / 'runtime-gpu/XRayGpuWorker.exe',
                 INSTALL_ROOT / 'runtime-gpu/python.exe',
                 INSTALL_ROOT / 'workspace/venvs/dino-directml/Scripts/python.exe'):
        if path.is_file():
            return path
    raise RuntimeError('這台電腦尚未安裝 DINO GPU 執行環境；請繼續使用 CPU')


def available():
    try:
        runtime_python()
        return True
    except RuntimeError:
        return False


def _exchange(process, result, header, payload):
    try:
        if header is not None:
            send(process.stdin, header, payload)
        result.put((True, receive(process.stdout)))
    except Exception as exc:
        result.put((False, exc))


class GpuSession:
    def __init__(self, path, sha256):
        self.lock = threading.Lock()
        executable=runtime_python()
        command=([str(executable)] if executable.name=='XRayGpuWorker.exe' else [str(executable),'-u',str(RESOURCE_ROOT/'gpu_worker.py')])
        self.process = subprocess.Popen(command+[str(Path(path).resolve()), sha256], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        _sessions.add(self)
        try:
            with self.lock:
                self.metadata, _ = self._request(timeout=90)
            self.device = self.metadata['device']
            self.runtime_version = self.metadata['version']
        except Exception:
            self.close()
            raise

    def _request(self, header=None, payload=b'', timeout=30):
        response = queue.Queue(maxsize=1)
        thread = threading.Thread(target=_exchange, args=(self.process, response, header, payload), daemon=True)
        thread.start()
        try:
            ok, result = response.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise RuntimeError('GPU 回應逾時，請切回 CPU 或檢查顯示卡狀態') from None
        if not ok:
            self.close()
            raise RuntimeError('GPU 執行失敗：' + str(result))
        if result[0].get('error'):
            self.close()
            raise RuntimeError('GPU 執行失敗：' + result[0]['error'])
        return result

    def get_inputs(self):
        return [SimpleNamespace(**n) for n in self.metadata['inputs']]

    def get_outputs(self):
        return [SimpleNamespace(**n) for n in self.metadata['outputs']]

    def get_providers(self):
        return self.metadata['providers']

    def run(self, output_names, inputs):
        if output_names is not None and output_names != [self.get_outputs()[0].name]:
            raise ValueError('不支援的 DINO 輸出名稱')
        if list(inputs) != [self.get_inputs()[0].name]:
            raise ValueError('DINO 輸入名稱不符')
        image = np.asarray(next(iter(inputs.values())), dtype='<f4', order='C')
        if image.shape != (1, 3, 224, 224):
            raise ValueError('GPU DINO 輸入必須為 [1,3,224,224]')
        with self.lock:
            header, data = self._request(dict(shape=list(image.shape)), image.tobytes())
        return [np.frombuffer(data, dtype='<f4').reshape(header['shape'])]

    def close(self):
        process = getattr(self, 'process', None)
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


@atexit.register
def _cleanup():
    for session in list(_sessions):
        session.close()
