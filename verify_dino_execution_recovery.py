"""A saved GPU setting must still permit CPU recovery after GPU becomes unavailable."""
import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
with TemporaryDirectory(prefix='xray-gpu-recovery-') as temp:
    config = Path(temp)/'config.json'
    config.write_text(json.dumps(dict(model_root=str(ROOT/'models'),allow_cpu_fallback=True)),encoding='utf-8')
    os.environ['XRAY_CONFIG']=str(config)
    os.environ['XRAY_WORKSPACE']=str(Path(temp)/'runtime')
    from station_settings import update_settings,read_settings
    update_settings(dino_execution='gpu', marker='unchanged')
    from app import app
    from model_manager import manager
    with patch('gpu_runtime.runtime_python',side_effect=RuntimeError('GPU missing after restart')):
        failed=manager.snapshot()
        assert failed.error and failed.info()['requested_backend']=='dino_onnx'
        with app.test_client() as client:
            response=client.post('/api/settings/dino-execution',json={'execution':'cpu'})
        assert response.status_code==200,response.json
        assert manager.snapshot().info()['execution']=='cpu'
        assert read_settings()['dino_execution']=='cpu' and read_settings()['marker']=='unchanged'
    result=dict(startup_gpu_failure_reported=True,cpu_recovery_available=True,settings_preserved=True)
    (ROOT/'workspace/gpu-investigation-20261104/startup-recovery-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: saved GPU unavailable on restart; CPU recovery works without GPU')
    # sqlite context managers commit but close on collection; release Windows file locks.
    import gc
    gc.collect()
