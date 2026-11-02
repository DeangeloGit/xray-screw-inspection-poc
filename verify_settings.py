"""Isolated UI API checks using a real, tiny ONNX CPU fixture (not trained weights)."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def fixture(classes=4):
    import onnx
    from onnx import helper, TensorProto
    graph=helper.make_graph([
        helper.make_node('Constant',[],['logits'],value=helper.make_tensor('scores',TensorProto.FLOAT,[1,classes],[0,5,0,0][:classes]))
    ],'test-only-constant-classifier',[helper.make_tensor_value_info('image',TensorProto.FLOAT,[1,3,224,224])],
        [helper.make_tensor_value_info('logits',TensorProto.FLOAT,[1,classes])])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],ir_version=10)
    onnx.checker.check_model(model)
    return model.SerializeToString()


def checks(root):
    import io
    import shutil
    import time
    import numpy as np
    from app import app, start_background
    from model_manager import manager, ModelManager
    from runtime_paths import DATA, RESOURCE_ROOT, MODEL_ROOT
    from library import importer, catalog, latest_results
    from station_settings import read_settings
    root=root.resolve()
    share=root/'設備照片'; share.mkdir(); (share/'子資料夾').mkdir()
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png',DATA/'ok_0.png')
    with app.test_client() as client:
        assert client.get('/settings').status_code==200
        assert '切換機型／來源' in client.get('/').text
        assert client.get('/static/settings.js').status_code==200
        listing=client.get('/api/settings/folders',query_string={'path':str(share)}).json
        assert listing['path']==str(share) and listing['directories'][0]['name']=='子資料夾'
        assert client.get('/api/settings/folders',query_string={'path':'relative/path'}).status_code==400
        assert client.post('/api/settings/acquisition',json={'enabled':True,'source':str(DATA)}).status_code==400
        assert client.post('/api/settings/acquisition',json={'enabled':True,'source':str(share),'stable_seconds':-1}).status_code==400
        saved=client.post('/api/settings/acquisition',json={'enabled':False,'source':str(share),'stable_seconds':0})
        assert saved.status_code==200 and read_settings()['acquisition']['source']==str(share)
        assert client.post('/api/settings/model',data={'model':(io.BytesIO(b'bad'),'bad.pth')}).status_code==400
        assert client.post('/api/settings/model',data={'model':(io.BytesIO(b'bad'),'bad.onnx'),'provider':'cpu'}).status_code==400
        assert not (MODEL_ROOT/'active.json').exists()
        valid=fixture()
        applied=client.post('/api/settings/model',data={'model':(io.BytesIO(valid),'測試模型.onnx'),'provider':'cpu','normalization':'unit'})
        assert applied.status_code==200,applied.json
        assert applied.json['model']['model_id']=='測試模型'
        prediction=manager.snapshot().classify(np.zeros((20,20),np.float32))
        assert prediction['label']=='cable' and prediction['status']=='shadow'
        active=(MODEL_ROOT/'active.json').read_bytes()
        identity=manager.snapshot().identity
        # Valid protobuf but incompatible classification output must not replace active state.
        rejected=client.post('/api/settings/model',data={'model':(io.BytesIO(fixture(2)),'wrong.onnx'),'provider':'cpu'})
        assert rejected.status_code==400 and (MODEL_ROOT/'active.json').read_bytes()==active
        assert manager.snapshot().identity==identity
        assert ModelManager(MODEL_ROOT).snapshot().identity==identity
        # Typical ResNet files exceed the old 40 MiB image limit. Reject as a bad model,
        # not as a 40 MiB photo upload; trained model files can be up to 512 MiB.
        rejected=client.post('/api/settings/model',data={'model':(io.BytesIO(b'x'*(41*1024*1024)),'large-invalid.onnx'),'provider':'cpu'})
        assert rejected.status_code==400,rejected.status_code
        # Start while disabled, then enable via UI without restarting the service.
        start_background()
        shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',share/'設備-001.png')
        enabled=client.post('/api/settings/acquisition',json={'enabled':True,'source':str(share),'stable_seconds':0})
        assert enabled.status_code==200
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            events=importer.metadata()
            if events and all(e['state']=='done' for e in events.values()): break
            time.sleep(.2)
        else: raise AssertionError((importer.info(),importer.metadata()))
        items=[x for x in catalog() if not x['is_reference']]
        result=latest_results()[items[0]['sha256']]
        assert result['candidates'] and all(x['classification']['label']=='cable' for x in result['candidates'])
        assert not result.get('image_review')
        assert client.post('/api/settings/acquisition',json={'enabled':False,'source':str(share),'stable_seconds':0}).status_code==200
        disabled=client.post('/api/settings/model',data={'disable':'true','provider':'cpu'})
        assert disabled.status_code==200 and manager.snapshot().manifest['backend']=='noop'
        assert ModelManager(MODEL_ROOT).snapshot().manifest['backend']=='noop'
        assert client.get('/api/settings').json['acquisition']['enabled'] is False
        importer.stop_event.set()
    # Preferences and effective model survive an actual new Python process.
    subprocess.run([sys.executable,'-c',"from station_settings import acquisition_config; from model_manager import manager; assert not acquisition_config()['enabled']; assert manager.snapshot().manifest['backend']=='noop'; print('PASS: UI settings persist across restart')"],check=True,env=os.environ)
    print('PASS: folder browser/save, self-import guard, live enable, real ONNX CPU apply/inference, invalid model keeps previous, >40MiB upload, UI disable and persistence')

if __name__=='__main__':
    if len(sys.argv)>1: checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace'))
            subprocess.run([sys.executable,__file__,str(root)],env=env,check=True)
