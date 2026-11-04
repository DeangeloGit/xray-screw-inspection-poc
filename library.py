"""Content-based local photo library and reproducible analysis cache."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from detector import ROOT, detect, DETECTOR_VERSION
from runtime_paths import DATA, OUTPUTS, RESOURCE_ROOT, STATE
from model_manager import manager
from machine_profiles import selected_profile, matches, profiles
from review_workflow import effective_review
from acquisition import Importer
from station_settings import source_scope, in_source, detection_threshold

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


def catalog(scope=None):
    scope = scope or source_scope()
    groups = {}
    reference_hashes = {digest(Path(p['reference'])) for p in profiles() if Path(p['reference']).is_file()}
    imported = importer.metadata()
    for path in DATA.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if not path.resolve().is_relative_to(DATA.resolve()):
            continue
        relative = path.relative_to(DATA).as_posix()
        if relative.startswith('incoming/'):
            if relative not in imported:
                continue  # Ignore uncommitted snapshots after interrupted imports.
            if not in_source(imported[relative]['source_path'], scope['path']):
                continue
        elif scope['path'] and not relative.startswith('uploads/' + scope['id'] + '/'):
            continue  # Demo/local files and uploads from other sources are retained, not shown.

        if any(s.startswith('.') for s in path.relative_to(DATA).parts):
            continue
        groups.setdefault(digest(path), []).append(relative)
    items = []
    for sha, aliases in groups.items():
        aliases.sort(key=lambda s: (Path(s).stem.startswith('ng_'), natural_key(s)))
        filename = aliases[0]
        items.append(dict(id=sha[:16], sha256=sha, filename=filename, aliases=aliases,
                          is_reference=sha in reference_hashes,
                          display_name=imported.get(filename, {}).get('original_filename', filename),
                          events=[dict(filename=imported.get(alias, {}).get('original_filename', alias),
                                       source_path=imported.get(alias, {}).get('source_path', str((DATA/alias).resolve())),
                                       local_path=str((DATA/alias).resolve()),
                                       acquired_at=imported.get(alias, {}).get('acquired_at', '')) for alias in aliases]))
    return sorted(items, key=lambda s: (s['is_reference'], natural_key(s['display_name'])))


def select_sample(value):
    for item in catalog():
        if value == item['id'] or value in item['aliases'] or any(
                value == Path(alias).stem for alias in item['aliases']):
            return item
    raise ValueError('找不到照片，請重新掃描 data 資料夾')


def analysis_key(sha, threshold=.13, model_snapshot=None, profile=None):
    profile = profile or selected_profile()
    snapshot = model_snapshot or manager.snapshot()
    build = RESOURCE_ROOT/'build_fingerprint.txt'
    engine = build.read_text(encoding='utf-8').strip() if build.is_file() else '|'.join(digest(RESOURCE_ROOT/p) for p in ('detector.py','registration_candidate.py','single_reference_evidence.py','wire_review.py','model_manager.py','model_adapters.py','library.py','machine_profiles.py','detection_runtime.py','brightness_fit.py','dino_adapter.py','dino_paired_optimized.py','paired_geometry.py'))
    ref = profile['reference_sha256'] + '|' + profile['id']
    return hashlib.sha256(f'{engine}|{ref}|{sha}|{float(threshold):.8f}|{snapshot.identity}|{snapshot.error}|{snapshot.requested}'.encode()).hexdigest()


def cached_result(item, threshold=.13, model_snapshot=None, profile=None):
    key = analysis_key(item['sha256'], threshold, model_snapshot, profile)
    path = OUTPUTS/key[:12]/'result.json'
    if path.is_file():
        result = json.loads(path.read_text(encoding='utf-8'))
        if result.get('cache_key') == key:
            return result
    return None


def analysis_failures(profile=None):
    profile = profile or selected_profile()
    with sqlite3.connect(STATE/'results.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS failures (sha TEXT, machine TEXT, reference TEXT, error TEXT, at TEXT, PRIMARY KEY(sha,machine,reference))')
        return {sha:dict(error=error,at=at) for sha,error,at in db.execute(
            'SELECT sha,error,at FROM failures WHERE machine=? AND reference=?',
            (profile['id'],profile['reference_sha256']))}


def record_analysis_failure(sha, profile, error=None):
    analysis_failures(profile)  # Create the table when upgrading a workspace.
    with sqlite3.connect(STATE/'results.sqlite3') as db:
        if error is None:
            db.execute('DELETE FROM failures WHERE sha=? AND machine=? AND reference=?',
                       (sha,profile['id'],profile['reference_sha256']))
        else:
            db.execute('INSERT OR REPLACE INTO failures VALUES(?,?,?,?,?)',
                       (sha,profile['id'],profile['reference_sha256'],str(error),datetime.now(timezone.utc).isoformat()))


def analyze_file(path, filename, threshold=None, sample_id=None, profile=None):
    profile = profile or selected_profile()
    threshold = detection_threshold(profile['id']) if threshold is None else threshold
    sha = digest(path)
    snapshot = manager.snapshot()
    key = analysis_key(sha, threshold, snapshot, profile)
    item = dict(sha256=sha)
    result = cached_result(item, threshold, snapshot, profile)
    if result is not None:
        record_analysis_failure(sha, profile)
        remember_result(result)
        return dict(result, image_review=effective_review(result))
    try:
        result = detect(profile['reference'], path, key[:12], threshold, model_snapshot=snapshot)
    except Exception as error:
        record_analysis_failure(sha, profile, error)
        raise
    record_analysis_failure(sha, profile)
    result.update(machine=profile, cache_key=key, source_sha256=sha, source_file=filename,
                  sample_id=sample_id, analyzed_at=datetime.now(timezone.utc).isoformat())
    save_result(result)
    remember_result(result)
    return result


def analyze_sample(item, threshold=None, profile=None):
    return analyze_file(DATA/item['filename'], item['filename'], threshold, item['id'], profile)


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
        db.execute('INSERT OR REPLACE INTO heads VALUES(?,?)', (result['source_sha256'] + '|' + result.get('machine',{}).get('id','default') + '|' + result.get('machine',{}).get('reference_sha256',''), result['name']))


def latest_results(profile=None):
    """Historical results remain reviewable after model/code updates; never reuse as new cache."""
    profile = profile or selected_profile()
    threshold = detection_threshold(profile['id'])
    results = {}
    for path in OUTPUTS.glob('*/result.json'):
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('cache_key', '')[:12] != result.get('name'):
                continue
            if result.get('version') != DETECTOR_VERSION or not matches(result, profile) or result.get('threshold', .13) != threshold:
                continue
            sha = result.get('source_sha256')
            if sha and result.get('analyzed_at', '') >= results.get(sha, {}).get('analyzed_at', ''):
                results[sha] = result
        except (OSError, ValueError):
            continue
    with sqlite3.connect(STATE/'results.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS heads (sha TEXT PRIMARY KEY, run TEXT)')
        for head, name in db.execute('SELECT sha,run FROM heads'):
            sha = head.split('|')[0]
            if not re.fullmatch('[a-f0-9]{12}', name):
                continue
            try:
                selected = json.loads((OUTPUTS/name/'result.json').read_text(encoding='utf-8'))
                if selected.get('version') == DETECTOR_VERSION and selected.get('source_sha256') == sha and selected.get('cache_key','')[:12] == name and matches(selected, profile) and selected.get('threshold', .13) == threshold:
                    results[sha] = selected
            except (OSError, ValueError):
                pass
    return results


def public_catalog(profile=None):
    profile = profile or selected_profile()
    scope = source_scope()
    items = catalog(scope)
    history = latest_results(profile)
    failures = analysis_failures(profile)
    for item in items:
        result = history.get(item['sha256'])
        item['analysis_error'] = failures.get(item['sha256'],{}).get('error') if result is None else None
        item.pop('sha256')
        if result is None:
            item['analysis'] = None
        else:
            review = effective_review(result)
            item['analysis'] = dict(name=result['name'], high=result['high_count'],
                                    total=result['proposal_count'], warning=result['alignment_warning'],
                                    reviewed=len(result.get('human_reviews', {})),
                                    image_review=review)
    return dict(items=items, file_count=sum(len(s['aliases']) for s in items),
                unique_count=len(items), model_fingerprint=manager.snapshot().identity, detector_version=DETECTOR_VERSION, detection_threshold=detection_threshold(profile['id']), source=scope, reference=profile.get('reference_name',Path(profile['reference']).name if profile['id']=='default' else profile['name']+' 正常參考圖'), machine=profile)
