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


def validate_threshold(value):
    if type(value) not in (int, float) or not .03 <= value <= .40:
        raise ValueError('差分門檻需為 0.03 至 0.40 的數值')
    return float(value)


def detection_threshold(profile_id=None):
    settings = read_settings()
    profile_id = profile_id or settings.get('selected_machine', 'default')
    # Keep the former shared value as the baseline for machines not yet tuned.
    return validate_threshold(settings.get('machine_thresholds', {}).get(
        profile_id, settings.get('detection_threshold', .13)))


def save_machine_threshold(profile_id, threshold):
    with LOCK:
        values = dict(read_settings().get('machine_thresholds', {}))
        values[profile_id] = validate_threshold(threshold)
        update_settings(machine_thresholds=values)
