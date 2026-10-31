"""Isolated integration checks: paths, hot swap, read-only import, report guards."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def checks(root):
    root = root.resolve()
    import csv
    import io
    import shutil
    import numpy as np
    import cv2
    from runtime_paths import DATA, OUTPUTS, WORK_ROOT, RESOURCE_ROOT, MODEL_ROOT
    from model_manager import ModelManager
    from acquisition import Importer
    import library
    from app import app
    assert WORK_ROOT == root/'workspace' and RESOURCE_ROOT != WORK_ROOT
    # Fully isolated workspace; real reference is used only as a test fixture.
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png', DATA/'ok_0.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png', DATA/'test.png')
    m = ModelManager(MODEL_ROOT)
    assert m.snapshot().classify(np.zeros((10,10),np.float32))['status'] == 'disabled'
    first = m.snapshot()
    version = MODEL_ROOT/'new-noop'; version.mkdir(parents=True)
    manifest = dict(schema_version=1,model_id='new-noop',backend='noop',
                    preprocessing='source-gray-percentile-crop-v1',classes=['screw','cable','structure','uncertain'])
    (version/'manifest.json').write_text(json.dumps(manifest))
    active = MODEL_ROOT/'active.json'
    active.write_text(json.dumps(dict(schema_version=1,version_directory='new-noop')))
    second = m.snapshot()
    assert second.manifest['model_id']=='new-noop' and first.identity != second.identity
    assert first.classify(np.zeros((2,2)))['model_id']=='noop-v1'
    active.write_text('{')
    broken = m.snapshot()
    assert broken.error and broken.identity==second.identity
    active.write_text(json.dumps(dict(schema_version=1,version_directory='../outside')))
    assert m.snapshot().error
    active.write_text(json.dumps(dict(schema_version=1,version_directory='new-noop')))
    assert not m.snapshot().error
    # Adapter contract checks use a fake runtime, not a claim of ONNX/CUDA hardware validation.
    import hashlib
    import types
    from unittest.mock import patch
    model_file=version/'model.onnx'; model_file.write_bytes(b'test-runtime-fixture')
    onnx_manifest=dict(manifest,backend='onnx',file='model.onnx',sha256=hashlib.sha256(model_file.read_bytes()).hexdigest(),
                       input_size=[224,224],mean=[0,0,0],std=[1,1,1],output='logits',provider_policy='require_cuda')
    class FakeSession:
        def __init__(self,*args,**kwargs): pass
        def disable_fallback(self): pass
        def get_providers(self): return ['CUDAExecutionProvider','CPUExecutionProvider']
        def get_inputs(self): return [types.SimpleNamespace(name='image',type='tensor(float)',shape=[1,3,224,224])]
        def get_outputs(self): return [types.SimpleNamespace(type='tensor(float)')]
        def run(self,outputs,inputs): return [np.array([[0,5,0,0]],np.float32)]
    runtime=types.SimpleNamespace(get_available_providers=lambda:['CUDAExecutionProvider'],InferenceSession=FakeSession)
    (version/'manifest.json').write_text(json.dumps(onnx_manifest))
    with patch.dict(sys.modules,{'onnxruntime':runtime}):
        shadow=m.snapshot()
        prediction=shadow.classify(np.zeros((30,30),np.float32))
        assert prediction['label']=='cable' and prediction['status']=='shadow' and prediction['action']=='manual_review'
        onnx_manifest['sha256']='incorrect'
        (version/'manifest.json').write_text(json.dumps(onnx_manifest))
        assert m.snapshot().error and m.snapshot().identity==shadow.identity
    (version/'manifest.json').write_text(json.dumps(manifest))
    # Real candidate pipeline: noop attaches no probabilities and preserves manual workflow.
    with app.test_client() as client:
        result = client.post('/api/analyze', data={'sample':'test'}).json
        assert result['candidates'] and all(c['classification']['status']=='disabled' and c['classification']['probabilities'] is None for c in result['candidates'])
        assert client.get('/static/user.js').status_code == 200
        item = next(x for x in library.catalog() if not x['is_reference'])
        ids = [item['id']]
        assert client.post('/api/reports/screws',json={'sample_ids':ids}).status_code==409
        for candidate in result['candidates']:
            assert client.post('/api/review/'+result['name'],json={'id':candidate['id'],'label':'normal'}).status_code==200
        assert client.post('/api/image-review/'+result['name'],json={'decision':'uncertain'}).status_code==200
        assert client.post('/api/reports/screws',json={'sample_ids':ids}).status_code==409
        assert client.post('/api/image-review/'+result['name'],json={'decision':'screw'}).status_code==200
        report = client.post('/api/reports/screws',json={'sample_ids':ids})
        rows = list(csv.reader(io.StringIO(report.data.decode('utf-8-sig'))))
        assert report.status_code==200 and len(rows)==2 and rows[1][1]=='' and rows[1][2]=='test.png'
        assert rows[1][5]=='人工確認有掉落螺絲'
        assert list((WORK_ROOT/'reports').glob('*.json'))
        # Candidate edits invalidate completion and block export again.
        client.post('/api/review/'+result['name'],json={'id':1,'label':'normal'})
        assert client.post('/api/reports/screws',json={'sample_ids':ids}).status_code==409
        client.post('/api/image-review/'+result['name'],json={'decision':'no_screw_seen'})
        empty = client.post('/api/reports/screws',json={'sample_ids':ids})
        assert empty.status_code==200 and empty.headers['X-Screw-Rows']=='0'
        # Model activation does not destroy historical reviews.
        manifest['model_id']='another-noop'
        (version/'manifest.json').write_text(json.dumps(manifest))
        listing=client.get('/api/samples').json
        assert next(x for x in listing['items'] if x['id']==item['id'])['analysis']['image_review']['decision']=='no_screw_seen'
        assert client.get('/api/samples/'+item['id']+'/result').json['name']==result['name']
        assert client.get('/api/station').status_code==200
        changed = client.post('/api/analyze',data={'sample':'test'}).json
        assert changed['name'] != result['name'] and 'image_review' not in changed
        manifest['model_id']='new-noop'
        (version/'manifest.json').write_text(json.dumps(manifest))
        restored = client.post('/api/analyze',data={'sample':'test'}).json
        assert restored['name']==result['name']
        assert client.get('/api/samples/'+item['id']+'/result').json['image_review']['decision']=='no_screw_seen'

    # Import completion, restart, source filename reuse and retry.
    source=root/'share'; source.mkdir()
    incoming=root/'import-data'; incoming.mkdir()
    state=root/'import-state'
    config=dict(enabled=True,source=str(source),stable_seconds=10)
    worker=Importer(config,incoming,state)
    file=source/'機台照片.png'
    ok,blob=cv2.imencode('.png',np.ones((128,128),np.uint16))
    file.write_bytes(blob.tobytes()); original=file.read_bytes()
    worker.scan_once(now=0); worker.scan_once(now=5)
    assert not list(incoming.rglob('*.png'))
    worker.scan_once(now=11)
    assert len(worker.metadata())==1 and file.read_bytes()==original
    worker.scan_once(now=30)
    assert len(worker.metadata())==1
    worker=Importer(config,incoming,state)
    worker.scan_once(now=40); assert len(worker.metadata())==1
    ok,blob=cv2.imencode('.png',np.zeros((128,128),np.uint16)); file.write_bytes(blob.tobytes())
    worker.scan_once(now=50); worker.scan_once(now=61)
    assert len(worker.metadata())==2, 'same source path must retain both acquisition events'
    def failure(*args): raise ValueError('test failure')
    worker.analyze=failure; worker.process_pending()
    assert all(x['state']=='analysis_error' for x in worker.metadata().values())
    worker.analyze=lambda *args:None; worker.process_pending()
    assert all(x['state']=='done' for x in worker.metadata().values())
    bad=source/'unfinished.png'; bad.write_bytes(b'not an image')
    worker.scan_once(now=70); worker.scan_once(now=81)
    assert len(worker.metadata())==2 and worker.info()['counts']['retry']==1
    # Production scan subprocess obeys station environment and returns bounded status.
    worker2=Importer()
    worker2.isolated_scan()
    assert worker2.status['state']=='disabled'
    # End-to-end automatic acquisition through the production subprocess and app callback.
    real_share=root/'real-share'; real_share.mkdir()
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',real_share/'device-photo.png')
    config_path=Path(os.environ['XRAY_CONFIG'])
    station=json.loads(config_path.read_text())
    station['acquisition']=dict(enabled=True,source=str(real_share),stable_seconds=0,poll_seconds=1,scan_timeout_seconds=20)
    config_path.write_text(json.dumps(station))
    code = """
import time
from app import start_background
from library import importer, public_catalog
start_background()
deadline=time.monotonic()+45
while time.monotonic()<deadline:
    events=importer.metadata()
    if events and all(x['state']=='done' for x in events.values()):
        items=public_catalog()['items']
        assert any(x.get('display_name')=='device-photo.png' and x['analysis'] for x in items)
        importer.stop_event.set()
        print('PASS: automatic source polling -> local snapshot -> analysis -> photo catalog')
        break
    time.sleep(.2)
else:
    raise AssertionError((importer.info(),importer.metadata()))
"""
    subprocess.run([sys.executable,'-c',code],env=os.environ,check=True,timeout=55)
    from reports import safe_cell
    assert safe_cell('=HYPERLINK("bad")').startswith("'")
    print('PASS: isolated paths, noop hot-swap/rollback, real candidates, retained manual reviews, guarded CSV/SN, read-only import stability/restart/source-history/retry, worker process')

if __name__ == '__main__':
    if len(sys.argv)>1:
        checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace'))
            subprocess.run([sys.executable,__file__,str(root)],env=env,check=True)
