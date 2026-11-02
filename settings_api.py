"""Operator settings: browse a station folder and validate/apply a single ONNX file."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import uuid
from flask import Blueprint, jsonify, request
from runtime_paths import DATA, OUTPUTS, WORK_ROOT, MODEL_ROOT, RESOURCE_ROOT, STATE, SETTINGS
from station_settings import acquisition_config, update_settings, cpu_allowed
from model_manager import CLASSES, PREPROCESSING, ModelManager, manager

settings_api = Blueprint('settings_api',__name__)
apply_lock = threading.Lock()

def absolute_folder(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('請選擇取圖資料夾')
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError('請使用完整資料夾路徑')
    return path.resolve()

def validate_source(path):
    # Prevent a source from containing imported snapshots and recursively importing itself.
    for forbidden in (WORK_ROOT, DATA, OUTPUTS, STATE, MODEL_ROOT):
        target = forbidden.resolve()
        if path == target or target.is_relative_to(path) or path.is_relative_to(target):
            raise ValueError('取圖來源需位於工作資料及模型資料夾以外，避免重複取圖')

def config_info():
    c = acquisition_config()
    return dict(acquisition=dict(enabled=c.get('enabled',False),source=c.get('source',''),
                                 stable_seconds=c.get('stable_seconds',15)),
                model=manager.snapshot().info(),default_provider=SETTINGS.get('default_provider','cpu' if sys.platform=='darwin' else 'require_cuda'))

@settings_api.get('/api/settings')
def get_settings():
    return jsonify(config_info())

@settings_api.get('/api/settings/folders')
def folders():
    try:
        raw=request.args.get('path')
        path=absolute_folder(raw) if raw else Path.home()
        directories=[]
        with os.scandir(path) as entries:
            for entry in entries:
                if not entry.name.startswith('.') and entry.is_dir(follow_symlinks=False):
                    directories.append(dict(name=entry.name,path=str(Path(entry.path))))
        return jsonify(path=str(path),parent=str(path.parent),directories=sorted(directories,key=lambda x:x['name'].casefold()))
    except (OSError,ValueError) as exc:
        return jsonify(error='無法開啟資料夾：'+str(exc)),400

@settings_api.post('/api/settings/acquisition')
def set_acquisition():
    body=request.get_json(silent=True)
    try:
        if not isinstance(body,dict) or type(body.get('enabled')) is not bool:
            raise ValueError('無效的取圖設定')
        config=acquisition_config()
        enabled=body['enabled']
        value=body.get('source',config.get('source',''))
        if value or enabled:
            path=absolute_folder(value); validate_source(path)
            source=str(path)
        else:
            source=''
        stable=body.get('stable_seconds',config.get('stable_seconds',15))
        if type(stable) not in (int,float) or not 0 <= stable <= 3600:
            raise ValueError('寫入等待秒數需介於 0 與 3600')
        update_settings(acquisition=dict(config,enabled=enabled,source=source,stable_seconds=stable))
        return jsonify(saved=True,acquisition=acquisition_config(),message='已儲存，照片清單已切換至此來源；新照片於下一次掃描並等待寫入穩定後顯示，已開始的照片會先處理完。')
    except (ValueError,OSError) as exc:
        return jsonify(error=str(exc)),400

@settings_api.post('/api/settings/model')
def apply_model():
    with apply_lock:
        upload=request.files.get('model')
        disable=request.form.get('disable')=='true'
        provider=request.form.get('provider','require_cuda')
        if provider not in ('cpu','require_cuda'):
            return jsonify(error='請選擇 CPU 或 NVIDIA GPU'),400
        if not disable and (not upload or not upload.filename.lower().endswith('.onnx')):
            return jsonify(error='請選擇符合本系統規格的 .onnx 模型檔案'),400
        token='ui-'+uuid.uuid4().hex
        staging=MODEL_ROOT/('.staging-'+token)
        directory=staging/token
        committed=False
        old_cpu=cpu_allowed()
        preferences_changed=False
        try:
            directory.mkdir(parents=True)
            manifest=dict(schema_version=1,model_id='未啟用 AI' if disable else Path(upload.filename.replace('\\','/')).stem,
                          backend='noop' if disable else 'onnx',preprocessing=PREPROCESSING,classes=CLASSES)
            if not disable:
                model_path=directory/'model.onnx'
                upload.save(model_path)
                normalization=request.form.get('normalization','imagenet')
                if normalization not in ('imagenet','unit'):
                    raise ValueError('不支援的影像正規化方式')
                manifest.update(file='model.onnx',sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                                input_size=[224,224],mean=[0.485,0.456,0.406] if normalization=='imagenet' else [0,0,0],
                                std=[0.229,0.224,0.225] if normalization=='imagenet' else [1,1,1],
                                output='logits',provider_policy=provider)
            (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
            selection=dict(schema_version=1,version_directory=token)
            (staging/'active.json').write_text(json.dumps(selection),encoding='utf-8')
            validator=ModelManager(staging,allow_cpu=provider=='cpu')
            candidate=validator.snapshot()
            if candidate.error:
                raise ValueError(candidate.error)
            # Nothing becomes active until validation succeeded. Existing results are untouched.
            os.replace(directory,MODEL_ROOT/token)
            update_settings(allow_cpu_fallback=provider=='cpu')
            preferences_changed=True
            pointer=MODEL_ROOT/('.active-'+uuid.uuid4().hex+'.tmp')
            try:
                pointer.write_text(json.dumps(selection),encoding='utf-8')
                with manager.lock:
                    os.replace(pointer,MODEL_ROOT/'active.json')
                    manager.current=candidate
                    manager.signature=validator.signature
            finally:
                pointer.unlink(missing_ok=True)
            committed=True
            effective=candidate
            return jsonify(applied=True,model=effective.info(),message='已停用 AI，保留人工複判。' if disable else '模型已套用，從下一張新分析開始使用；現有照片與複判紀錄不會被覆寫。')
        except (ValueError,OSError) as exc:
            if preferences_changed and not committed:
                update_settings(allow_cpu_fallback=old_cpu)
            return jsonify(error='無法套用模型：'+str(exc)+'。原模型及人工複判保持可用。'),400
        finally:
            shutil.rmtree(staging,ignore_errors=True)
            if not committed:
                shutil.rmtree(MODEL_ROOT/token,ignore_errors=True)
