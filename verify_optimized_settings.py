"""Isolated real device switches must preserve r3 features and other preferences."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
MODEL='dino-paired-optimized-47-20261104-r3'


def main(output):
    with tempfile.TemporaryDirectory(prefix='xray-r3-devices-') as temp:
        root=Path(temp);models=root/'models';models.mkdir()
        shutil.copytree(ROOT/'models'/MODEL,models/MODEL)
        (models/'active.json').write_text(json.dumps(dict(schema_version=1,version_directory=MODEL)),encoding='utf-8')
        config=root/'config.json';config.write_text(json.dumps(dict(model_root=str(models),allow_cpu_fallback=True)),encoding='utf-8')
        os.environ['XRAY_CONFIG']=str(config);os.environ['XRAY_WORKSPACE']=str(root/'runtime')
        from station_settings import update_settings,read_settings
        update_settings(acquisition=dict(enabled=False,source='unchanged'),marker='preserve-me',dino_execution='cpu')
        from app import app
        from model_manager import manager,ModelManager
        import numpy as np
        from PIL import Image
        crop=np.asarray(Image.open(next((models/MODEL/'examples').glob('*.png'))).convert('L'),np.float32)/255
        cpu=manager.snapshot();assert not cpu.error
        with app.test_client() as client:
            gpu_response=client.post('/api/settings/dino-execution',json=dict(execution='gpu'))
            assert gpu_response.status_code==200,gpu_response.json
            gpu=manager.snapshot();assert gpu.feature_bank.shape==(112,8,2,384)
            restart=ModelManager().snapshot();assert not restart.error and restart.identity==gpu.identity
            restart.session.close()
            a=cpu.classify(crop,reference_crop=crop);b=gpu.classify(crop,reference_crop=crop)
            assert a['status']==b['status']=='active' and a['action']==b['action']=='discard'
            back=client.post('/api/settings/dino-execution',json=dict(execution='cpu'))
            assert back.status_code==200 and manager.snapshot().identity==cpu.identity
            assert gpu.classify(crop,reference_crop=crop)['status']=='active'
            before=read_settings()
            with patch('gpu_runtime.runtime_python',side_effect=RuntimeError('diagnostic missing GPU')):
                failed=client.post('/api/settings/dino-execution',json=dict(execution='gpu'))
                assert failed.status_code==400 and read_settings()==before
                assert manager.snapshot().identity==cpu.identity
            assert before['marker']=='preserve-me' and before['acquisition']==dict(enabled=False,source='unchanged')
            gpu.session.close()
        report=dict(success=True,cpu_model=cpu.info(),gpu_model=gpu.info(),selection_persisted=True,
                    other_settings_unchanged=True,failed_switch_rolled_back=True,existing_snapshot_survives_switch=True,
                    feature_bank_retained=True,production_state_written=False)
        Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS: r3 CPU/GPU switching, persistence, failure recovery and unchanged preferences')
        import gc;gc.collect()


if __name__=='__main__':main(sys.argv[1])
