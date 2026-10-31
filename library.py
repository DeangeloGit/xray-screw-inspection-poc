"""Content-based local photo library and reproducible analysis cache."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from detector import ROOT, detect
from runtime_paths import DATA, OUTPUTS, REFERENCE, RESOURCE_ROOT, STATE
from model_manager import manager
from acquisition import Importer

importer = Importer()
SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}
_hash_cache = {}


def digest(path):
    path = Path(path)
    st = path.stat()
    key = (str(path.resolve()), st.st_mtime_ns, st.st_size)
    if key not in _hash_cache:
        _hash_cache[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _hash_cache[key]


def natural_key(value):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', value)]


def catalog():
    groups = {}
    imported = importer.metadata()
    for path in DATA.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if not path.resolve().is_relative_to(DATA.resolve()):
            continue
        relative = path.relative_to(DATA).as_posix()
        if relative.startswith('incoming/') and relative not in imported:
            continue  # Ignore uncommitted snapshots after interrupted imports.
        if any(s.startswith('.') for s in path.relative_to(DATA).parts):
            continue
        groups.setdefault(digest(path), []).append(relative)
    items = []
    for sha, aliases in groups.items():
        aliases.sort(key=lambda s: (Path(s).stem.startswith('ng_'), natural_key(s)))
        filename = aliases[0]
        items.append(dict(id=sha[:16], sha256=sha, filename=filename, aliases=aliases,
                          is_reference=any((DATA/alias).resolve() == REFERENCE.resolve() for alias in aliases),
                          display_name=imported.get(filename, {}).get('original_filename', filename),
                          events=[dict(filename=imported.get(alias, {}).get('original_filename', alias),
                                       source_path=imported.get(alias, {}).get('source_path', str((DATA/alias).resolve())),
                                       local_path=str((DATA/alias).resolve()),
                                       acquired_at=imported.get(alias, {}).get('acquired_at', '')) for alias in aliases]))
    return sorted(items, key=lambda s: (s['is_reference'], natural_key(s['filename'])))


def select_sample(value):
    for item in catalog():
        if value == item['id'] or value in item['aliases'] or any(
                value == Path(alias).stem for alias in item['aliases']):
            return item
    raise ValueError('找不到照片，請重新掃描 data 資料夾')


def analysis_key(sha, threshold=.13, model_snapshot=None):
    snapshot = model_snapshot or manager.snapshot()
    build = RESOURCE_ROOT/'build_fingerprint.txt'
    engine = build.read_text(encoding='utf-8').strip() if build.is_file() else '|'.join(digest(RESOURCE_ROOT/p) for p in ('detector.py','model_manager.py','library.py'))
    if not REFERENCE.is_file():
        raise ValueError('缺少正常參考圖，請設定 reference 或放入 data/ok_0.png')
    ref = digest(REFERENCE)
    return hashlib.sha256(f'{engine}|{ref}|{sha}|{float(threshold):.8f}|{snapshot.identity}|{snapshot.error}|{snapshot.requested}'.encode()).hexdigest()


def cached_result(item, threshold=.13, model_snapshot=None):
    key = analysis_key(item['sha256'], threshold, model_snapshot)
    path = OUTPUTS/key[:12]/'result.json'
    if path.is_file():
        result = json.loads(path.read_text(encoding='utf-8'))
        if result.get('cache_key') == key:
            return result
    return None


def analyze_file(path, filename, threshold=.13, sample_id=None):
    sha = digest(path)
    snapshot = manager.snapshot()
    key = analysis_key(sha, threshold, snapshot)
    item = dict(sha256=sha)
    result = cached_result(item, threshold, snapshot)
    if result is not None:
        remember_result(result)
        return result
    result = detect(REFERENCE, path, key[:12], threshold, model_snapshot=snapshot)
    result.update(cache_key=key, source_sha256=sha, source_file=filename,
                  sample_id=sample_id, analyzed_at=datetime.now(timezone.utc).isoformat())
    save_result(result)
    remember_result(result)
    return result


def analyze_sample(item, threshold=.13):
    return analyze_file(DATA/item['filename'], item['filename'], threshold, item['id'])


def save_result(result):
    path = OUTPUTS/result['name']/'result.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def remember_result(result):
    # Explicit reanalysis can reuse an older matching cache after rollback. Remember the
    # chosen run instead of treating the greatest analysis timestamp as permanently active.
    with sqlite3.connect(STATE/'results.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS heads (sha TEXT PRIMARY KEY, run TEXT)')
        db.execute('INSERT OR REPLACE INTO heads VALUES(?,?)', (result['source_sha256'], result['name']))


def latest_results():
    """Historical results remain reviewable after model/code updates; never reuse as new cache."""
    results = {}
    for path in OUTPUTS.glob('*/result.json'):
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('cache_key', '')[:12] != result.get('name'):
                continue
            sha = result.get('source_sha256')
            if sha and result.get('analyzed_at', '') >= results.get(sha, {}).get('analyzed_at', ''):
                results[sha] = result
        except (OSError, ValueError):
            continue
    with sqlite3.connect(STATE/'results.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS heads (sha TEXT PRIMARY KEY, run TEXT)')
        for sha, name in db.execute('SELECT sha,run FROM heads'):
            if not re.fullmatch('[a-f0-9]{12}', name):
                continue
            try:
                selected = json.loads((OUTPUTS/name/'result.json').read_text(encoding='utf-8'))
                if selected.get('source_sha256') == sha and selected.get('cache_key','')[:12] == name:
                    results[sha] = selected
            except (OSError, ValueError):
                pass
    return results


def public_catalog():
    items = catalog()
    history = latest_results()
    for item in items:
        result = history.get(item['sha256'])
        item.pop('sha256')
        if result is None:
            item['analysis'] = None
        else:
            review = result.get('image_review', {})
            item['analysis'] = dict(name=result['name'], high=result['high_count'],
                                    total=result['proposal_count'], warning=result['alignment_warning'],
                                    reviewed=len(result.get('human_reviews', {})),
                                    image_review=review)
    return dict(items=items, file_count=sum(len(s['aliases']) for s in items),
                unique_count=len(items), reference='ok_0.png')
