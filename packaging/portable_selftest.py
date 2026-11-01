"""On-device diagnostics, isolated from the operator's photos, models and reviews."""
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from tempfile import TemporaryDirectory
import traceback


def run(root):
    report=dict(platform=platform.platform(),python=sys.version,checks=[],success=False)
    (root/'logs').mkdir(exist_ok=True)
    try:
        with TemporaryDirectory(prefix='xray-selftest-') as temporary:
            temporary=Path(temporary)
            config=temporary/'station.json'
            config.write_text(json.dumps(dict(workspace=str(temporary/'workspace'),model_root=str(temporary/'models'))),encoding='utf-8')
            os.environ['XRAY_CONFIG']=str(config)
            os.environ['XRAY_WORKSPACE']=str(temporary/'workspace')
            import cv2,numpy,onnxruntime
            report['checks'].append('OpenCV, NumPy and ONNX Runtime imports')
            report['providers']=onnxruntime.get_available_providers()
            from app import app
            from runtime_paths import DATA
            for name in ('ok_0.png','ng_5.png','ng_9.png'):
                shutil.copyfile(root/'workspace/data'/name,DATA/name)
            with app.test_client() as client:
                for url in ('/','/settings','/engineer','/help/user','/static/settings.js'):
                    assert client.get(url).status_code==200,url
                report['checks'].append('Web UI, settings and manuals')
                for sample in ('ok_0','ng_5','ng_9'):
                    result=client.post('/api/analyze',data={'sample':sample})
                    assert result.status_code==200,result.json
                    assert (result.json['proposal_count']==0) == (sample=='ok_0')
                report['checks'].append('Normal reference and two sample image analyses')
                model=Path(__file__).with_name('selftest.onnx').read_bytes()
                response=client.post('/api/settings/model',data={'model':(io.BytesIO(model),'diagnostic-only.onnx'),'provider':'cpu'})
                assert response.status_code==200,response.json
                from model_manager import manager
                prediction=manager.snapshot().classify(numpy.zeros((64,64),numpy.float32))
                assert prediction['label']=='cable' and prediction['status']=='shadow',prediction
                report['checks'].append('Actual ONNX CPU model upload and inference (diagnostic fixture)')
            report['success']=True
    except Exception:
        report['error']=traceback.format_exc()
    path=root/'logs/windows-selftest.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print('Saved: '+str(path),flush=True)
    return 0 if report['success'] else 1
