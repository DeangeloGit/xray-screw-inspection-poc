"""Persistent inspection machine types and immutable reference images."""
import hashlib
import uuid
from pathlib import Path
from runtime_paths import STATE, REFERENCE
from station_settings import read_settings, update_settings, LOCK, detection_threshold

REFERENCES = STATE / 'machine-references'


def profiles():
    settings = read_settings()
    return [dict(id='default', name='預設機型（原 V1）', reference=str(REFERENCE))] + settings.get('machine_profiles', [])


def selected_profile(profile_id=None):
    profile_id = profile_id or read_settings().get('selected_machine', 'default')
    for item in profiles():
        if item['id'] == profile_id:
            result = dict(item)
            path = Path(result['reference'])
            if not path.is_file():
                raise ValueError('此機型尚無可用的正常參考圖，請至工程模式指定')
            result['reference_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result
    raise ValueError('找不到檢測機型，請重新選擇')


def public_profiles():
    selected = read_settings().get('selected_machine', 'default')
    items = []
    for item in profiles():
        path = Path(item['reference'])
        items.append(dict(id=item['id'], name=item['name'], reference_name=item.get('reference_name',path.name if item['id']=='default' else item['name']+' 正常參考圖'),
                          threshold=detection_threshold(item['id']), ready=path.is_file(), reference_url='/api/machines/'+item['id']+'/reference'))
    return dict(items=items, selected=selected)


def save_profile(name, upload, profile_id=None):
    from detector import read
    name = str(name or '').strip()
    if not name or len(name) > 80:
        raise ValueError('請輸入 1 至 80 字的機型名稱')
    with LOCK:
        items = read_settings().get('machine_profiles', [])
        if profile_id == 'default':
            raise ValueError('原 V1 參考圖保留不變，請新增機型')
        if profile_id and not any(p['id'] == profile_id for p in items):
            raise ValueError('找不到機型')
        if any(p['name'] == name and p['id'] != profile_id for p in profiles()):
            raise ValueError('機型名稱已存在')
        if not upload or not upload.filename:
            raise ValueError('請選取正常參考圖')
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'):
            raise ValueError('參考圖需為 PNG、JPEG 或 TIFF')
        REFERENCES.mkdir(parents=True, exist_ok=True)
        path = REFERENCES / (uuid.uuid4().hex + suffix)
        try:
            upload.save(path)
            read(path)  # Decode before publishing the new profile.
            item = dict(id=profile_id or uuid.uuid4().hex[:16], name=name, reference=str(path), reference_name=Path(upload.filename.replace('\\','/')).name)
            items = [item if p['id'] == profile_id else p for p in items] if profile_id else items + [item]
            update_settings(machine_profiles=items)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return item


def select_profile(profile_id):
    with LOCK:
        profile = selected_profile(profile_id)
        update_settings(selected_machine=profile['id'])
        return profile


def matches(result, profile):
    machine = result.get('machine')
    if machine is None:
        return profile['id'] == 'default'  # Legacy V1 histories remain reviewable.
    return machine['id'] == profile['id'] and machine['reference_sha256'] == profile['reference_sha256']
