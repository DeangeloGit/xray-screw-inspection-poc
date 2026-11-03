"""Run real packaged HTTP and DINO checks with isolated, disposable state."""
import io
import gc
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import traceback
import urllib.request


def run(root):
    report = dict(success=False, executable=sys.executable, checks=[])
    try:
        with tempfile.TemporaryDirectory(prefix='xray-portable-check-') as scratch:
            scratch = Path(scratch)
            models = scratch / 'models'
            shutil.copytree(root / 'models', models)
            config = scratch / 'station.json'
            config.write_text(json.dumps(dict(workspace=str(scratch / 'workspace'),
                model_root=str(models), allow_cpu_fallback=True,
                acquisition=dict(enabled=False, source=''))), encoding='utf-8')
            os.environ['XRAY_CONFIG'] = str(config)
            os.environ['XRAY_WORKSPACE'] = str(scratch / 'workspace')
            settings = json.loads((root / 'workspace/state/ui_settings.json').read_text(encoding='utf-8'))
            for profile in settings['machine_profiles']:
                profile['reference'] = str(root / 'workspace/state/machine-references' / Path(profile['reference']).name)
                assert Path(profile['reference']).is_file()
            state = scratch / 'workspace/state'
            state.mkdir(parents=True)
            (state / 'ui_settings.json').write_text(json.dumps(settings), encoding='utf-8')
            from app import app
            from launch import bind_server
            from model_manager import manager
            from PIL import Image
            import numpy as np
            active = manager.snapshot()
            assert not active.error, active.info()
            assert len(active.manifest['example_bank']['screw']['ids']) == 47
            assert len(active.manifest['example_bank']['normal']['ids']) == 65
            example = next((models / active.requested / 'examples').glob('*.png'))
            crop = np.asarray(Image.open(example).convert('L'), np.float32) / 255
            from dino_adapter import PAIRED_POLICY
            assert active.manifest['decision_policy'] == PAIRED_POLICY
            pred = active.classify(crop, reference_crop=crop)
            assert pred['status'] == 'active', pred
            assert pred['action'] == 'discard' and 'paired_evidence' in pred
            missing = active.classify(crop)
            assert missing['status'] == 'error' and missing['action'] == 'manual_review'
            report['model'] = active.info()
            report['checks'].append('47+65 paired DINO: both images inferred, identical pair excluded, missing reference kept for review')
            server, _ = bind_server(app, ports=(0,))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                base = f'http://127.0.0.1:{server.port}'
                for path in ('/api/health', '/engineer?tab=ai', '/static/dino-examples.js',
                             '/static/dino-examples.css', '/api/dino/examples'):
                    with http.open(base + path, timeout=30) as response:
                        body = response.read()
                        assert response.status == 200 and body, path
                        if '/engineer' in path:
                            assert b'dino-examples-root' in body
                report['checks'].append('Actual loopback HTTP, engineering page and integrated DINO manager')
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
            with app.test_client() as client:
                listing = client.get('/api/dino/examples?model=' + active.requested)
                assert listing.status_code == 200, listing.json
                data = listing.json
                assert len(data['examples']) == 112, data.keys()
                assert all(x['available'] for x in data['examples'])
                preview = client.post('/api/dino/preview', data=dict(model=active.requested,
                    image=(io.BytesIO(example.read_bytes()), 'screw.png')))
                assert preview.status_code == 200, preview.data[:500]
                assert Image.open(io.BytesIO(preview.data)).size == (224, 224)
                from machine_profiles import public_profiles
                assert sum(p['ready'] for p in public_profiles()['items']) == 4
                old = manager.snapshot('dino-examples-a3b8c97aa539')
                assert not old.error and len(old.manifest['example_bank']['screw']['ids']) == 31
                report['checks'].append('112 example images, actual-input preview and original DINO rollback model')
                # Exercise saved example changes inside the disposable copy only.
                keep = [x['id'] for x in data['examples']]
                unchanged = (models / 'active.json').read_bytes()
                built = client.post('/api/dino/build', data=dict(model=active.requested,
                    name='Portable verification copy', keep=json.dumps(keep)))
                assert built.status_code == 200, built.json
                assert (models / 'active.json').read_bytes() == unchanged
                new = built.json['directory']
                assert json.loads((models / new / 'manifest.json').read_text())['decision_policy'] == PAIRED_POLICY
                for version in [new, active.requested]:
                    selected = client.post('/api/settings/models/select', json=dict(directory=version))
                    assert selected.status_code == 200, selected.json
                    assert manager.snapshot().requested == version
                report['checks'].append('Four machine references; save new example version, activate and switch back')
            # SQLite context managers commit but leave cyclic connections for GC.
            gc.collect()
        report['success'] = True
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
    (root / 'logs').mkdir(exist_ok=True)
    (root / 'logs/portable-selftest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['success'] else 1
