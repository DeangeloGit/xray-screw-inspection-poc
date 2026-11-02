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
import threading
import subprocess


def run(root):
    report=dict(platform=platform.platform(),python=sys.version,checks=[],success=False)
    log_root=Path(os.environ.get('XRAY_USER_ROOT',str(root)))
    (log_root/'logs').mkdir(parents=True,exist_ok=True)
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
            from launch import bind_server,ready,workspace_identity
            from runtime_paths import WORK_ROOT
            server,failures=bind_server(app)
            serving=threading.Thread(target=server.serve_forever,daemon=True);serving.start()
            try:
                url='http://127.0.0.1:'+str(server.port)
                assert ready(url,workspace_identity(WORK_ROOT)),'本機 HTTP 就緒檢查未通過'
                report['local_http']=dict(url=url,bind_failures=failures,proxy_free=True)
                report['checks'].append('Actual local TCP bind and proxy-free HTTP health check')
            finally:
                server.shutdown();server.server_close()
            from runtime_paths import DATA
            samples_present=all((root/'workspace/data'/name).is_file() for name in ('ok_0.png','ng_5.png','ng_9.png'))
            if samples_present:
                for name in ('ok_0.png','ng_5.png','ng_9.png'):
                    shutil.copyfile(root/'workspace/data'/name,DATA/name)
            with app.test_client() as client:
                for url in ('/','/settings','/engineer','/help/user','/static/settings.js'):
                    assert client.get(url).status_code==200,url
                report['checks'].append('Web UI, settings and manuals')
                if samples_present:
                    for sample in ('ok_0','ng_5','ng_9'):
                        result=client.post('/api/analyze',data={'sample':sample})
                        assert result.status_code==200,result.json
                        assert (result.json['proposal_count']==0) == (sample=='ok_0')
                    report['checks'].append('Normal reference and two sample image analyses')
                else:
                    report['skipped']=['Original X-ray sample analyses: public package contains no input photos']
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
    if sys.platform=='win32':
        try:
            ports=subprocess.run(['netsh','interface','ipv4','show','excludedportrange','protocol=tcp'],capture_output=True,timeout=5)
            report['excluded_ports']=ports.stdout.decode('utf-8',errors='replace')
        except Exception as exc:
            report['excluded_ports_error']=str(exc)
    path=log_root/'logs/windows-selftest.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print('Saved: '+str(path),flush=True)
    return 0 if report['success'] else 1
