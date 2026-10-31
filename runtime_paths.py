"""Packaged resources are read-only; station data lives outside the bundle."""
import json
import os
import sys
from pathlib import Path

RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
INSTALL_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_ROOT
CONFIG_PATH = Path(os.environ.get('XRAY_CONFIG', INSTALL_ROOT / 'config/station.json')).resolve()
SETTINGS = json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.is_file() else {}

def configured_path(value):
    p = Path(value).expanduser()
    return p if p.is_absolute() else CONFIG_PATH.parent / p

WORK_ROOT = Path(os.environ['XRAY_WORKSPACE']).expanduser().resolve() if os.environ.get('XRAY_WORKSPACE') else configured_path(SETTINGS['workspace']) if SETTINGS.get('workspace') else (INSTALL_ROOT / 'workspace' if getattr(sys, 'frozen', False) else RESOURCE_ROOT)
DATA = WORK_ROOT / 'data'
OUTPUTS = WORK_ROOT / 'outputs'
STATE = WORK_ROOT / 'state'
REFERENCE = configured_path(SETTINGS['reference']) if SETTINGS.get('reference') else DATA / 'ok_0.png'
MODEL_ROOT = configured_path(SETTINGS['model_root']) if SETTINGS.get('model_root') else INSTALL_ROOT / 'models'
for directory in (DATA, OUTPUTS, STATE):
    directory.mkdir(parents=True, exist_ok=True)
