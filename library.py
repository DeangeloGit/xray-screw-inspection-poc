"""Content-based local photo library and reproducible analysis cache."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
from detector import ROOT, detect

DATA = ROOT/'data'
OUTPUTS = ROOT/'outputs'
REFERENCE = DATA/'ok_0.png'
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
    for path in DATA.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if not path.resolve().is_relative_to(DATA.resolve()):
            continue
        relative = path.relative_to(DATA).as_posix()
        if any(s.startswith('.') for s in path.relative_to(DATA).parts):
            continue
        groups.setdefault(digest(path), []).append(relative)
    items = []
    for sha, aliases in groups.items():
        aliases.sort(key=lambda s: (Path(s).stem.startswith('ng_'), natural_key(s)))
        filename = aliases[0]
        items.append(dict(id=sha[:16], sha256=sha, filename=filename, aliases=aliases,
                          is_reference='ok_0.png' in aliases))
    return sorted(items, key=lambda s: (s['is_reference'], natural_key(s['filename'])))


def select_sample(value):
    for item in catalog():
        if value == item['id'] or value in item['aliases'] or any(
                value == Path(alias).stem for alias in item['aliases']):
            return item
    raise ValueError('找不到照片，請重新掃描 data 資料夾')


def analysis_key(sha, threshold=.13):
    engine = digest(ROOT/'detector.py')
    ref = digest(REFERENCE)
    return hashlib.sha256(f'{engine}|{ref}|{sha}|{float(threshold):.8f}'.encode()).hexdigest()


def cached_result(item, threshold=.13):
    key = analysis_key(item['sha256'], threshold)
    path = OUTPUTS/key[:12]/'result.json'
    if path.is_file():
        result = json.loads(path.read_text())
        if result.get('cache_key') == key:
            return result
    return None


def analyze_file(path, filename, threshold=.13, sample_id=None):
    sha = digest(path)
    key = analysis_key(sha, threshold)
    item = dict(sha256=sha)
    result = cached_result(item, threshold)
    if result is not None:
        return result
    result = detect(REFERENCE, path, key[:12], threshold)
    result.update(cache_key=key, source_sha256=sha, source_file=filename,
                  sample_id=sample_id, analyzed_at=datetime.now(timezone.utc).isoformat())
    save_result(result)
    return result


def analyze_sample(item, threshold=.13):
    return analyze_file(DATA/item['filename'], item['filename'], threshold, item['id'])


def save_result(result):
    path = OUTPUTS/result['name']/'result.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    tmp.replace(path)


def public_catalog():
    items = catalog()
    for item in items:
        result = cached_result(item)
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
