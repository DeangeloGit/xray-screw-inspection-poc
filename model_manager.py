"""Immutable per-image model snapshots. Noop is explicit, never a fake classifier."""
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from runtime_paths import MODEL_ROOT, SETTINGS
from station_settings import cpu_allowed

CLASSES = ['screw', 'cable', 'structure', 'uncertain']
PREPROCESSING = 'source-gray-percentile-crop-v1'

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

@dataclass(frozen=True)
class Snapshot:
    manifest: dict
    identity: str
    session: object = None
    error: str = None
    requested: str = None

    def info(self):
        return dict(model_id=self.manifest['model_id'], fingerprint=self.identity,
                    backend=self.manifest['backend'], requested=self.requested,
                    error=self.error, mode='shadow',
                    providers=self.session.get_providers() if self.session else [])

    def classify(self, crop):
        base = dict(model_id=self.manifest['model_id'], action='manual_review')
        if self.session is None:
            return dict(base, status='error' if self.error else 'disabled', label='uncertain', probabilities=None)
        try:
            m = self.manifest
            if m['backend'] in ('clip_onnx','yolo_onnx'):
                from model_adapters import classify
                return dict(base, status='shadow', **classify(m, self.session, crop))
            image = cv2.resize(crop.astype(np.float32), (224, 224), interpolation=cv2.INTER_LINEAR)
            image = np.repeat(image[None], 3, axis=0)
            image = (image - np.asarray(m['mean'], np.float32)[:, None, None]) / np.asarray(m['std'], np.float32)[:, None, None]
            logits = np.asarray(self.session.run(None, {self.session.get_inputs()[0].name: image[None]})[0])
            if logits.shape != (1, 4) or not np.isfinite(logits).all():
                raise ValueError('模型輸出必須為有限數值 [1,4]')
            scores = np.exp(logits[0] - logits[0].max()); scores /= scores.sum()
            return dict(base, status='shadow', label=CLASSES[int(scores.argmax())],
                        probabilities=dict(zip(CLASSES, map(float, scores))))
        except Exception as exc:
            return dict(base, status='error', label='uncertain', probabilities=None, error=str(exc))


def noop(error=None, requested=None):
    m = dict(model_id='noop-v1', backend='noop', preprocessing=PREPROCESSING, classes=CLASSES)
    return Snapshot(m, fingerprint(m), error=error, requested=requested)

class ModelManager:
    def __init__(self, root=MODEL_ROOT, allow_cpu=None):
        self.root = Path(root)
        self.allow_cpu = allow_cpu
        self.lock = threading.Lock()
        self.current = noop()
        self.signature = None

    def snapshot(self, version_directory=None):
        with self.lock:
            active = self.root / 'active.json'
            if version_directory is None and not active.exists():
                # A deliberately unconfigured station uses noop; removal after activation is an error.
                if self.signature is None:
                    return self.current
                return Snapshot(self.current.manifest, self.current.identity, self.current.session,
                                '找不到 active.json，保留先前模型', self.current.requested)
            requested = None
            try:
                pointer = (json.dumps(dict(schema_version=1,version_directory=version_directory)).encode() if version_directory is not None else active.read_bytes())
                selection = json.loads(pointer)
                if selection.get('schema_version') != 1:
                    raise ValueError('不支援的啟用設定版本')
                requested = selection['version_directory']
                if not isinstance(requested, str) or Path(requested).name != requested or requested in ('.', '..') or '\\' in requested:
                    raise ValueError('無效模型版本目錄')
                directory = (self.root / requested).resolve()
                if directory.parent != self.root.resolve():
                    raise ValueError('模型目錄不可指向外部路徑')
                manifest_bytes = (directory / 'manifest.json').read_bytes()
                m = json.loads(manifest_bytes)
                if m.get('schema_version') != 1 or (m.get('backend') in ('noop','onnx') and (m.get('preprocessing') != PREPROCESSING or m.get('classes') != CLASSES)) or (m.get('backend') in ('clip_onnx','yolo_onnx') and m.get('preprocessing') != 'aligned-gray-tight12-v1'):
                    raise ValueError('不支援的模型契約或類別')
                if not isinstance(m.get('model_id'), str) or not m['model_id']:
                    raise ValueError('缺少 model_id')
                session = None
                signature = fingerprint([pointer.hex(), manifest_bytes.hex()])
                if m['backend'] in ('onnx','clip_onnx','yolo_onnx'):
                    filename = m['file']
                    path = (directory / filename).resolve()
                    if path.parent != directory or path.suffix.lower() != '.onnx':
                        raise ValueError('模型必須為版本目錄內的 ONNX 檔')
                    # Immutable version folders: check stat changes as well as active/manifest changes.
                    stat = path.stat()
                    signature = fingerprint([signature, stat.st_size, stat.st_mtime_ns])
                elif m['backend'] != 'noop':
                    raise ValueError('不支援的模型 backend')
                if signature == self.signature:
                    return self.current
                if m['backend'] in ('onnx','clip_onnx','yolo_onnx'):
                    payload = path.read_bytes()
                    if hashlib.sha256(payload).hexdigest() != m['sha256']:
                        raise ValueError('模型 SHA-256 不符')
                    if m['backend']=='onnx':
                        if m.get('input_size') != [224, 224] or m.get('output') != 'logits':
                            raise ValueError('不支援的模型輸入輸出契約')
                        for field in ('mean', 'std'):
                            a = np.asarray(m[field], dtype=float)
                            if a.shape != (3,) or not np.isfinite(a).all() or (field == 'std' and np.any(a <= 0)):
                                raise ValueError('無效的正規化設定')
                    import onnxruntime as ort
                    require_cuda = m.get('provider_policy', 'require_cuda') == 'require_cuda'
                    if m.get('provider_policy', 'require_cuda') not in ('require_cuda', 'cpu'):
                        raise ValueError('無效 provider_policy')
                    if not require_cuda and not (cpu_allowed() if self.allow_cpu is None else self.allow_cpu):
                        raise ValueError('站台未允許 CPU 模型')
                    if require_cuda and 'CUDAExecutionProvider' not in ort.get_available_providers():
                        raise ValueError('CUDA provider 不可用')
                    if require_cuda and hasattr(ort, 'preload_dlls'):
                        ort.preload_dlls()
                    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if require_cuda else ['CPUExecutionProvider']
                    # Load bytes so the validated file cannot change between hashing and session creation.
                    options = ort.SessionOptions()
                    options.intra_op_num_threads = 4
                    session = ort.InferenceSession(payload, sess_options=options, providers=providers)
                    session.disable_fallback()
                    if require_cuda and session.get_providers()[0] != 'CUDAExecutionProvider':
                        raise ValueError('CUDA session 未成功建立')
                    if m['backend']=='onnx':
                        inputs, outputs = session.get_inputs(), session.get_outputs()
                        if len(inputs) != 1 or inputs[0].type != 'tensor(float)' or inputs[0].shape not in ([1,3,224,224], ['N',3,224,224]):
                            raise ValueError('模型輸入必須為 float32 [1,3,224,224] 或 [N,3,224,224]')
                        if len(outputs) != 1 or outputs[0].type != 'tensor(float)':
                            raise ValueError('模型必須只有一個 float32 輸出')
                        test = session.run(None, {inputs[0].name: np.zeros((1,3,224,224), np.float32)})[0]
                        if np.asarray(test).shape != (1,4) or not np.isfinite(test).all():
                            raise ValueError('模型測試輸出不符')
                    else:
                        from model_adapters import validate
                        validate(m, session)
                policy = None
                if m['backend']=='clip_onnx':
                    from model_adapters import CLIP_DECISION_POLICY, CLIP_REVIEW_MARGIN
                    policy = [CLIP_DECISION_POLICY, CLIP_REVIEW_MARGIN]
                identity_parts = [m, m.get('sha256'), session.get_providers() if session else []]
                if policy is not None:
                    identity_parts.append(policy)
                identity = fingerprint(identity_parts)
                self.current = Snapshot(m, identity, session, requested=requested)
                self.signature = signature
                return self.current
            except Exception as exc:
                # Keep the previous validated session, clearly reporting requested/effective versions.
                return Snapshot(self.current.manifest, self.current.identity, self.current.session, ('尚未安裝模型推論套件，請先安裝 onnxruntime（Mac／CPU）或 onnxruntime-gpu（IPC／GPU）' if isinstance(exc, ModuleNotFoundError) and exc.name == 'onnxruntime' else str(exc)), requested)

manager = ModelManager()
