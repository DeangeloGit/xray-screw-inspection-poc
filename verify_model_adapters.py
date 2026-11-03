"""Isolated model replacement tests; synthetic weights are never installed in the real station."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np


def fixture(shape, values):
    import onnx
    from onnx import helper,TensorProto
    graph=helper.make_graph([helper.make_node('Constant',[],['output'],value=helper.make_tensor('values',TensorProto.FLOAT,shape,values))],
        'test-only-yolo',[helper.make_tensor_value_info('image',TensorProto.FLOAT,[1,3,640,640])],
        [helper.make_tensor_value_info('output',TensorProto.FLOAT,shape)])
    return helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],ir_version=10).SerializeToString()


def checks():
    from app import app
    from model_manager import manager,ModelManager
    from runtime_paths import MODEL_ROOT
    with app.test_client() as client:
        values=[320,320,100,100,.8,.1]
        response=client.post('/api/settings/model',data=dict(model=(io.BytesIO(fixture([1,6,1],values)),'fixture.onnx'),
            backend='yolo_onnx',provider='cpu',classes='screw,cable',screw_class_id='0',input_size='640',confidence='.25'))
        assert response.status_code==200,response.json
        snapshot=manager.snapshot();a=snapshot.classify(np.ones((40,80),np.float32))
        assert a['action']=='manual_review' and a['status']=='active'
        assert a['label']=='screw' and abs(a['screw_score']-.8)<1e-5,a
        identity=snapshot.identity;pointer=(MODEL_ROOT/'active.json').read_bytes()
        versions=client.get('/api/settings/models').json['models'];version=versions[0]['directory']
        # Wrong layout and wrong class order count must preserve the previous session.
        response=client.post('/api/settings/model',data=dict(model=(io.BytesIO(fixture([1,1,6],values)),'wrong.onnx'),backend='yolo_onnx',provider='cpu',classes='screw,cable'))
        assert response.status_code==400 and (MODEL_ROOT/'active.json').read_bytes()==pointer
        assert manager.snapshot().identity==identity
        assert client.post('/api/settings/models/select',json={'directory':'../other'}).status_code==400
        assert client.post('/api/settings/model',data={'disable':'true','provider':'cpu'}).status_code==200
        assert manager.snapshot().manifest['backend']=='noop'
        response=client.post('/api/settings/models/select',json={'directory':version})
        assert response.status_code==200,response.json
        assert manager.snapshot().identity==identity
        assert ModelManager(MODEL_ROOT).snapshot().identity==identity
        # Uploaded labels can place the screw class after another class.
        response=client.post('/api/settings/model',data=dict(model=(io.BytesIO(fixture([1,6,1],values)),'order.onnx'),backend='yolo_onnx',provider='cpu',classes='cable,screw',screw_class_id='1'))
        assert response.status_code==200,response.json
        assert manager.snapshot().classify(np.ones((80,40),np.float32))['label']=='non_screw'
        assert manager.snapshot().classify(np.ones((80,40),np.float32))['action']=='discard'
        assert snapshot.classify(np.ones((40,80),np.float32))['label']=='screw', 'in-flight snapshot changed'
        # Detection elsewhere in the crop must not keep the candidate.
        assert snapshot.classify(np.ones((80,80),np.float32),candidate_box=[0,0,10,10])['action']=='discard'
        assert snapshot.classify(np.ones((80,80),np.float32),candidate_box=[35,35,45,45])['action']=='manual_review'
        response=client.post('/api/settings/model',data=dict(model=(io.BytesIO(fixture([1,1,6],[270,270,370,370,.9,0])),'postprocessed.onnx'),backend='yolo_onnx',provider='cpu',classes='screw',yolo_layout='end2end'))
        assert response.status_code==200,response.json
        assert manager.snapshot().classify(np.ones((80,80),np.float32),candidate_box=[35,35,45,45])['label']=='screw'
        assert ModelManager(MODEL_ROOT).snapshot().identity==manager.snapshot().identity
        assert 'yolo-layout' in client.get('/engineer?tab=ai').text
        assert 'model-backend' in client.get('/engineer?tab=ai').text
    print('PASS: YOLO inference, class mapping, invalid-model rollback, disable/reselect, immutable snapshot and restart')


if __name__=='__main__':
    if '--child' in sys.argv:checks()
    else:
        with tempfile.TemporaryDirectory(prefix='xray-model-adapters-') as d:
            root=Path(d);config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace'),PYTHONUTF8='1')
            subprocess.run([sys.executable,__file__,'--child'],env=env,check=True)
