"""Real CPU/GPU paired decisions, persistent UI selection and failure rollback; isolated state."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix='xray-device-') as temp:
        work = Path(temp)
        config = work / 'station.json'
        config.write_text(json.dumps(dict(model_root=str(ROOT / 'models'), allow_cpu_fallback=True)), encoding='utf-8')
        os.environ['XRAY_CONFIG'] = str(config)
        os.environ['XRAY_WORKSPACE'] = str(work / 'runtime')
        import numpy as np
        from PIL import Image
        from app import app
        from model_manager import manager, ModelManager
        from station_settings import read_settings, update_settings
        import gpu_runtime
        active = (ROOT / 'models/active.json').read_bytes()
        update_settings(acquisition=dict(enabled=False, source=''), marker='preserve-me')
        cpu = manager.snapshot()
        assert not cpu.error, cpu.error
        assert cpu.info()['execution'] == 'cpu'
        with app.test_client() as client:
            assert 'DINO 執行方式' in client.get('/settings').text
            assert client.get('/api/settings').json['dino_execution'] == 'cpu'
            assert client.post('/api/settings/dino-execution', json={'execution': 'bad'}).status_code == 400
            started = time.perf_counter()
            applied = client.post('/api/settings/dino-execution', json={'execution': 'gpu'})
            assert applied.status_code == 200, applied.json
            gpu = manager.snapshot()
            assert gpu.info()['execution'] == 'gpu' and gpu.identity != cpu.identity
            assert gpu.manifest == cpu.manifest
            assert manager.snapshot() is gpu, 'no worker reload on every poll'
            print('GPU applied:', gpu.info(), flush=True)
            restored = ModelManager().snapshot()
            assert not restored.error and restored.identity == gpu.identity
            restored.session.close()
            rows = json.loads((ROOT / 'workspace/dino-learn-joint-20261103/results.json').read_text(encoding='utf-8'))
            results = []
            source = None
            for z in rows:
                if z['source'] != source:
                    source = z['source']
                    ref, tar = [np.asarray(Image.open(Path(source) / f).convert('L'), np.float32) / 255
                                for f in ('reference.png', 'aligned.png')]
                x, y, w, h = [z['c'][k] for k in ('x','y','w','h')]
                region = (slice(max(0, y-12), y+h+12), slice(max(0, x-12), x+w+12))
                a = cpu.classify(tar[region], reference_crop=ref[region])
                b = gpu.classify(tar[region], reference_crop=ref[region])
                assert a['status'] == b['status'] == 'active', (a, b)
                changed = [side for side in ('target', 'reference') if
                           a['paired_evidence'][side]['label'] != b['paired_evidence'][side]['label']]
                assert not changed and a['action'] == b['action'], z['key']
                results.append(dict(number=z['number'], key=z['key'], cpu=a, gpu=b))
                if len(results) % 15 == 0:
                    print(f'Compared {len(results)}/{len(rows)} paired cases', flush=True)
            back = client.post('/api/settings/dino-execution', json={'execution':'cpu'})
            assert back.status_code == 200 and manager.snapshot().identity == cpu.identity
            # A photo already holding the previous GPU snapshot still completes after a switch.
            assert gpu.classify(tar[region], reference_crop=ref[region])['status'] == 'active'
            saved = read_settings()
            original = gpu_runtime.runtime_python
            def unavailable():
                raise RuntimeError('test: missing GPU runtime')
            gpu_runtime.runtime_python = unavailable
            try:
                failed = client.post('/api/settings/dino-execution', json={'execution':'gpu'})
                assert failed.status_code == 400 and '保留' in failed.json['error']
                assert read_settings() == saved and manager.snapshot().identity == cpu.identity
            finally:
                gpu_runtime.runtime_python = original
            assert read_settings()['marker'] == 'preserve-me'
            assert (ROOT / 'models/active.json').read_bytes() == active
            output = ROOT / 'workspace/gpu-investigation-20261104'
            (output / 'ui-gpu-verification.json').write_text(json.dumps(dict(
                cases=len(results), decision_changes=0, reference_and_target_checked=True,
                settings_persisted=True, failure_rollback=True, old_snapshot_survives_switch=True,
                formal_algorithm_unchanged=True, active_model_pointer_unchanged=True,
                device=gpu.info(), elapsed=time.perf_counter()-started, results=results),
                ensure_ascii=False, indent=2), encoding='utf-8')
            gpu.session.close()
            print('PASS: real GPU / CPU decisions, persistence, rollback and snapshot lifetime', flush=True)
        import gc
        gc.collect()


if __name__ == '__main__':
    main()
