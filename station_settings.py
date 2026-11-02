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


def source_scope(config=None):
    """A lexical identity: do not contact SMB just to identify the saved source."""
    import hashlib
    config = acquisition_config() if config is None else config
    source = config.get('source', '')
    source = os.path.normcase(os.path.abspath(os.path.expanduser(source))) if source else ''
    return dict(path=source, id=hashlib.sha256(source.encode('utf-8')).hexdigest()[:16] if source else 'local')


def in_source(path, root):
    if not root:
        return True
    path = os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False
