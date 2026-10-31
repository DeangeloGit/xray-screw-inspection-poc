"""UI preferences override station defaults without editing the installed resources."""
import json
import os
import threading
import uuid
from runtime_paths import STATE, SETTINGS

PATH = STATE / 'ui_settings.json'
LOCK = threading.RLock()

def read_settings():
    with LOCK:
        return json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}

def update_settings(**changes):
    with LOCK:
        settings = read_settings()
        settings.update(changes)
        temporary = PATH.with_name(uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temporary, PATH)
        finally:
            temporary.unlink(missing_ok=True)
        return settings

def acquisition_config():
    return dict(SETTINGS.get('acquisition',{}), **read_settings().get('acquisition',{}))

def cpu_allowed():
    return read_settings().get('allow_cpu_fallback', SETTINGS.get('allow_cpu_fallback',False))
