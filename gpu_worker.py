"""Persistent DirectML inference; separate environment leaves CPU installation intact."""
import hashlib
import sys
from pathlib import Path

from gpu_protocol import receive, send


def main():
    source, target = sys.stdin.buffer, sys.stdout.buffer
    try:
        import numpy as np
        import onnxruntime as ort
        from gpu_devices import nvidia_adapter
        payload = Path(sys.argv[1]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != sys.argv[2]:
            raise ValueError('GPU 模型 SHA-256 不符')
        adapter = nvidia_adapter()
        if 'DmlExecutionProvider' not in ort.get_available_providers():
            raise ValueError('GPU 環境未安裝 DirectML')
        options = ort.SessionOptions()
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = 4
        for name, value in [('batch_size', 1), ('num_channels', 3), ('height', 224), ('width', 224)]:
            options.add_free_dimension_override_by_name(name, value)
        session = ort.InferenceSession(payload, sess_options=options,
            providers=[('DmlExecutionProvider', {'device_id': str(adapter['index'])}), 'CPUExecutionProvider'])
        session.disable_fallback()
        if session.get_providers()[0] != 'DmlExecutionProvider':
            raise ValueError('未成功啟用 NVIDIA GPU')
        def describe(nodes):
            return [dict(name=n.name, type=n.type, shape=n.shape) for n in nodes]
        send(target, dict(inputs=describe(session.get_inputs()), outputs=describe(session.get_outputs()),
            providers=session.get_providers(), device=adapter['name'], version=ort.__version__))
        while True:
            header, data = receive(source)
            image = np.frombuffer(data, dtype='<f4').reshape(header['shape'])
            if image.shape != (1, 3, 224, 224):
                raise ValueError('GPU DINO 輸入尺寸錯誤')
            result = np.asarray(session.run(None, {session.get_inputs()[0].name: image})[0], dtype='<f4')
            send(target, dict(shape=list(result.shape)), result.tobytes())
    except EOFError:
        pass
    except Exception as exc:
        send(target, dict(error=str(exc) or type(exc).__name__))


if __name__ == '__main__':
    main()
