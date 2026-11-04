"""Versioned, offline station handoff. Python standard library only."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
import uuid
import zipfile

SCHEMA = 1
POLICY = 'dino-top3-target-and-reference-v1'
SKIP = {'__pycache__', '.DS_Store', 'local-server.json', 'mac-app.log', 'local-service.log'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or str(p) != name or p.is_absolute()
            or any(x in ('', '.', '..') or any(c in x for c in '<>:"|?*') or any(ord(c)<32 for c in x) or x.endswith((' ', '.'))
                   or x.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}
                   for x in p.parts)):
        raise ValueError('不安全或無法跨平台的檔名：' + name)
    return p


def resolve_setting(value, config):
    p = Path(value).expanduser()
    return (p if p.is_absolute() else config.parent / p).resolve()


def layout(root, config=None):
    root = Path(root).expanduser().resolve()
    config = Path(config).expanduser().resolve() if config else root / 'config/station.json'
    settings = read(config) if config.exists() else {}
    default_work = root / 'workspace/windows-check' if not config.exists() and (root/'workspace/windows-check/state/ui_settings.json').is_file() else root
    work = resolve_setting(settings['workspace'], config) if settings.get('workspace') else default_work
    models = resolve_setting(settings['model_root'], config) if settings.get('model_root') else root / 'models'
    ui = read(work / 'state/ui_settings.json') if (work / 'state/ui_settings.json').exists() else {}
    return dict(root=root, config=config, settings=settings, work=work, models=models, ui=ui)


def active_server(work):
    urls = ['http://127.0.0.1:8765', 'http://127.0.0.1:8766', 'http://127.0.0.1:18765']
    record = work / 'state/local-server.json'
    if record.exists():
        try:
            port = read(record)['port']
            if type(port) is int and 1 <= port <= 65535:
                urls.insert(0, 'http://127.0.0.1:' + str(port))
        except (ValueError, KeyError):
            pass
    identity = hashlib.sha256(os.path.normcase(str(work.resolve())).encode()).hexdigest()[:16]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in dict.fromkeys(urls):
        try:
            with opener.open(url + '/api/health', timeout=.3) as r:
                value = json.load(r)
            if value.get('service') == 'xray-poc' and value.get('workspace_id') == identity:
                return url
        except (OSError, ValueError):
            pass
    return None


def files_under(root):
    if not root.exists():
        return
    if root.is_symlink():
        raise ValueError('請先將連結轉為實際檔案：' + str(root))
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in dirs + names:
            if (Path(folder) / name).is_symlink():
                raise ValueError('資料含符號連結，請先整理：' + str(Path(folder) / name))
        for name in sorted(names):
            if name in SKIP or name.endswith(('-wal', '-shm', '.log', '.partial', '.tmp')):
                continue
            p = Path(folder) / name
            if not p.is_file():
                raise ValueError('不是一般檔案：' + str(p))
            yield p


def validate_station(base, require_dino=True, work=None, models=None):
    """Checks bytes/contracts; inference remains a separate runtime acceptance step."""
    base = Path(base)
    errors, warnings = [], []
    models = Path(models) if models is not None else base / 'models'
    work = Path(work) if work is not None else base / 'workspace'
    summary = {}
    try:
        pointer = read(models / 'active.json')
        if pointer.get('schema_version') != 1:
            raise ValueError('模型啟用指標版本不符')
        version = pointer['version_directory']
        if safe_name(version).parts != (version,):
            raise ValueError('模型版本必須是單一目錄')
        m = read(models / version / 'manifest.json')
        summary = dict(version=version, backend=m.get('backend'), decision_policy=m.get('decision_policy'))
        if m.get('backend') == 'dino_onnx':
            weight = safe_name(m['file'])
            if len(weight.parts) != 1:
                raise ValueError('模型權重必須直接位於版本目錄')
            if not (models / version / weight).is_file():
                errors.append('缺少 DINO ONNX 權重')
            elif sha(models / version / weight) != m.get('sha256'):
                errors.append('DINO ONNX 權重校驗失敗')
            counts = {k: len(m.get('example_bank', {}).get(k, {}).get('ids', [])) for k in ('screw', 'normal')}
            summary['examples'] = counts
            if counts != dict(screw=47, normal=65):
                errors.append('預設模型必須是 47 張螺絲＋65 張正常範例')
            if m.get('neighbors') != 3 or m.get('decision_margin') != 0 or m.get('input_size') != [224,224] or m.get('classes') != ['screw','non_screw']:
                errors.append('DINO 輸入或 top3 判斷契約不符')
            if m.get('decision_policy') != POLICY:
                errors.append('預設模型未啟用 DINO 雙圖規則')
            if m.get('feature_strategy'):
                if m['feature_strategy'] != 'contrast-global-local-half-v1':
                    errors.append('不支援的 DINO 特徵策略')
                feature = safe_name(m.get('feature_file',''))
                if len(feature.parts) != 1:
                    raise ValueError('r3 特徵檔必須直接位於模型版本目錄')
                feature_path = models / version / feature
                if not feature_path.is_file():
                    errors.append('缺少 r3 整體／局部特徵檔')
                elif sha(feature_path) != m.get('feature_sha256'):
                    errors.append('r3 整體／局部特徵檔校驗失敗')
            meta = read(models / version / 'examples.json')
            for label in ('screw', 'normal'):
                bank = m['example_bank'][label]
                vectors = bank.get('embeddings', [])
                if len(set(bank['ids'])) != len(bank['ids']) or len(vectors) != len(bank['ids']) or any(len(v) != 384 or any(not isinstance(n, (int,float)) or not math.isfinite(n) for n in v) or abs(sum(n*n for n in v)-1) > .003 for v in vectors):
                    errors.append('DINO 範例特徵庫數量或維度不符：' + label)
                for key in bank['ids']:
                    entry = meta.get(key, {})
                    name = entry.get('file', '')
                    if not name:
                        errors.append('缺少範例圖片索引：' + key)
                        continue
                    example = safe_name(name)
                    if len(example.parts) != 1:
                        raise ValueError('範例圖片必須直接位於 examples 目錄')
                    file = models / version / 'examples' / example
                    if not file.is_file() or sha(file) != entry.get('sha256'):
                        errors.append('範例圖片缺少或校驗失敗：' + key)
        elif require_dino:
            errors.append('缺少正式 DINO 47＋65 雙圖模型；目前為 ' + str(m.get('backend')))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        errors.append('模型缺件或格式不符：' + str(e))
    ui_path = work / 'state/ui_settings.json'
    if not ui_path.exists():
        errors.append('缺少使用者設定 state/ui_settings.json')
    else:
        ui = read(ui_path)
        if ui.get('selected_machine','default') == 'default' and not (work/'data/ok_0.png').is_file():
            warnings.append('預設機型沒有 data/ok_0.png；若使用自訂 reference，請另核對站台設定。')
        for p in ui.get('machine_profiles', []):
            ref = Path(p['reference'])
            if not ref.is_absolute():
                ref = base / ref
            if not ref.is_file():
                errors.append('缺少機種參照圖：' + p.get('name', p['id']))
    for name in ('data', 'outputs', 'state'):
        if not (work / name).is_dir():
            errors.append('缺少工作資料夾：' + name)
    for db in (work / 'state').glob('*.sqlite3'):
        try:
            with closing(sqlite3.connect(db.as_uri()+'?mode=ro', uri=True)) as con:
                if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    errors.append('資料庫完整性失敗：' + db.name)
                tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if db.name == 'acquisition.sqlite3' and 'events' in tables:
                    for (local,) in con.execute('SELECT local FROM events'):
                        try:
                            safe_name(local)
                            if not (work/'data'/local).is_file():
                                errors.append('缺少已匯入照片快照：'+local)
                        except ValueError:
                            errors.append('照片快照路徑不合法：'+str(local))
        except sqlite3.Error as e:
            errors.append('資料庫無法開啟：' + str(e))
    warnings.append('本檢查不等於 ONNX 實際推論或辨識準確率驗收。')
    return dict(ok=not errors, errors=errors, warnings=warnings, model=summary)


def collect(loc, extra):
    sources, mappings = {}, []
    def add_tree(source, relative):
        source = source.resolve()
        mappings.append(dict(old=str(source), relative=relative))
        for p in files_under(source):
            key = relative + '/' + p.relative_to(source).as_posix()
            safe_name(key)
            if key in sources and sources[key] != p:
                raise ValueError('資料位置衝突：' + key)
            sources[key] = p
    for name in ('data', 'outputs', 'state', 'reports', 'review'):
        add_tree(loc['work'] / name, 'workspace/' + name)
    add_tree(loc['models'], 'models')
    for name in ('archives','extra','handoff-history'):
        if (loc['root']/name).is_dir():
            add_tree(loc['root']/name,name)
    receipt=loc['root']/'IMPORT-RECEIPT.json'
    if receipt.is_file():
        sources['handoff-history/'+sha(receipt)+'.json']=receipt
    # Preserve private report/experiment folders; never recursively include checkpoints.
    private = loc['root'] / 'workspace'
    excluded = {'checkpoints','venvs','gpu-wheels','transfers','handoffs','.venv','node_modules'}
    if private.exists():
        for child in sorted(private.iterdir()):
            if child.is_dir() and child.name not in excluded | {'data','outputs','state','reports','review'} and not child.name.startswith('.') and not loc['work'].is_relative_to(child):
                add_tree(child, 'archives/workspace/' + child.name)
    # References may be outside the station tree (including original portable relative paths).
    references = [p['reference'] for p in loc['ui'].get('machine_profiles', [])]
    default_reference = resolve_setting(loc['settings']['reference'], loc['config']) if loc['settings'].get('reference') else loc['work'] / 'data/ok_0.png'
    if default_reference.is_file() or loc['ui'].get('selected_machine','default') == 'default':
        references.append(str(default_reference))
    for i, value in enumerate(dict.fromkeys(references)):
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = (loc['root'] / p).resolve()
        if not p.is_file():
            raise ValueError('缺少正常參照圖：' + str(p))
        if not any(p.is_relative_to(Path(m['old'])) for m in mappings):
            key = 'external/references/' + str(i) + p.suffix.lower()
            sources[key] = p
            mappings.append(dict(old=str(p), relative=key))
    acquisition = dict(loc['settings'].get('acquisition', {}), **loc['ui'].get('acquisition', {}))
    source = acquisition.get('source', '')
    if source:
        p = Path(source).expanduser().resolve()
        if not p.is_dir():
            raise ValueError('來源圖資無法讀取，完整移交不能略過：' + str(p))
        if p.is_relative_to(loc['work']) or loc['work'].is_relative_to(p):
            raise ValueError('外部取圖來源不可包含工作區或位於工作區內')
        add_tree(p, 'external/source')
    for i, p in enumerate(extra):
        p = Path(p).expanduser().resolve()
        if not p.is_dir():
            raise ValueError('附加資料夾不存在：' + str(p))
        add_tree(p, 'extra/' + str(i) + '-' + p.name)
    return sources, mappings, acquisition


def snapshot_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in ('.db', '.sqlite', '.sqlite3'):
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
        return
    before = source.stat()
    shutil.copyfile(source, target)
    os.utime(target, ns=(before.st_atime_ns,before.st_mtime_ns))
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or sha(source) != sha(target):
        raise ValueError('匯出期間資料變動，請關閉檢測程式後重試：' + str(source))


def rebase(value, mappings):
    if isinstance(value, dict):
        return {k: rebase(v, mappings) for k, v in value.items()}
    if isinstance(value, list):
        return [rebase(v, mappings) for v in value]
    if isinstance(value, str):
        normalized = value.replace('\\', '/')
        if Path(value).is_absolute() and Path(value).exists():
            normalized = str(Path(value).resolve()).replace('\\', '/')
        for old, new in mappings:
            old = old.replace('\\', '/').rstrip('/')
            if normalized == old or normalized.startswith(old + '/'):
                tail = normalized[len(old):].lstrip('/')
                return ((new.rstrip('/')+'/'+tail) if tail else new) if new.startswith('uploads/') else (str(Path(new).joinpath(*PurePosixPath(tail).parts)) if tail else str(new))
    return value


def export_bundle(root, output, config=None, extra=(), allow_incomplete=False):
    loc = layout(root, config)
    running = active_server(loc['work'])
    if running:
        raise ValueError('請先關閉此工作區的檢測服務再匯出：' + running)
    preflight = validate_station(loc['root'],work=loc['work'],models=loc['models'])
    if not preflight['ok'] and not allow_incomplete:
        raise ValueError('完整移交缺件：\n' + '\n'.join(preflight['errors']))
    output = Path(output).expanduser().resolve()
    if output.exists() or Path(str(output)+'.sha256').exists():
        raise ValueError('移交包名稱已存在，請用新名稱')
    files, mappings, acquisition = collect(loc, extra)
    if any(output.is_relative_to(Path(m['old'])) for m in mappings):
        raise ValueError('移交包請存到資料範圍以外的暫存資料夾或 Drive')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xray-export-') as tmp:
        stage = Path(tmp)
        for i, (name, source) in enumerate(sorted(files.items()), 1):
            snapshot_file(source, stage / name)
            if i % 500 == 0:
                print('已備份', i, '/', len(files), flush=True)
        # Store portable config rather than source-machine secrets/absolute settings.
        station = dict(loc['settings'], schema_version=1, workspace='../workspace', model_root='../models')
        if loc['settings'].get('reference'):
            station['reference']=str(resolve_setting(loc['settings']['reference'],loc['config']))
        write(stage/'config/station.json', station)
        for name in ('data', 'outputs', 'state', 'reports', 'review'):
            (stage / 'workspace' / name).mkdir(parents=True, exist_ok=True)
        # Validate with staged paths, without changing exported source records.
        path_map = sorted([(m['old'], str(stage/m['relative'])) for m in mappings], key=lambda p: -len(p[0]))
        ui_file = stage/'workspace/state/ui_settings.json'
        ui = read(ui_file) if ui_file.exists() else {}
        original_ui = ui_file.read_bytes() if ui_file.exists() else None
        write(ui_file, rebase(ui, path_map))
        validation = validate_station(stage)
        if original_ui is not None:
            ui_file.write_bytes(original_ui)
        else:
            ui_file.unlink()
        if not validation['ok'] and not allow_incomplete:
            raise ValueError('完整移交缺件：\n' + '\n'.join(validation['errors']))
        # Refuse a changing station even when individual files happened to copy cleanly.
        after_files, _, _ = collect(loc, extra)
        if files != after_files or any(p.stat().st_size != (stage/n).stat().st_size or
                sha(p) != sha(stage/n) for n,p in files.items()
                if p.suffix.lower() not in ('.db', '.sqlite', '.sqlite3')) or active_server(loc['work']):
            raise ValueError('匯出期間工作區有變動；未建立可交付資料包')
        try:
            commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=loc['root'],text=True,stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(['git','status','--porcelain'],cwd=loc['root'],text=True))
        except (OSError, subprocess.CalledProcessError):
            build = loc['root'] / 'BUILD-MANIFEST.json'
            receipt=loc['root']/'IMPORT-RECEIPT.json'
            commit = read(build).get('source_commit') if build.exists() else (read(receipt).get('source_commit') if receipt.exists() else None)
            dirty = None
        inventory = [dict(path=p.relative_to(stage).as_posix(),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha(p))
                     for p in sorted(stage.rglob('*')) if p.is_file()]
        manifest = dict(schema_version=SCHEMA,created_at=datetime.now(timezone.utc).isoformat(),
                        source_commit=commit,source_dirty=dirty,complete=validation['ok'],validation=validation,
                        mappings=mappings,source_acquisition=acquisition,source_scope_id=(hashlib.sha256(os.path.normcase(os.path.abspath(acquisition['source'])).encode()).hexdigest()[:16] if acquisition.get('source') else 'local'),
                        files=inventory,excluded=['程式與執行環境','歷史 checkpoint/venv/cache；可用 --extra 明確加入資料夾',
                        '服務紀錄、暫存檔、SQLite WAL/SHM（已做一致性備份）'])
        partial = output.with_name(output.name+'.'+uuid.uuid4().hex+'.partial')
        try:
            with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
                z.writestr('TRANSFER-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
                for row in inventory:
                    z.write(stage/row['path'],row['path'])
            # Verify archive before publishing; checksum file is written last.
            verify_archive(partial, require_sidecar=False)
            os.replace(partial,output)
            checksum = sha(output)
            sidecar = Path(str(output)+'.sha256')
            temp_sidecar = sidecar.with_name(sidecar.name+'.partial')
            temp_sidecar.write_text(checksum+'  '+output.name+'\n',encoding='utf-8')
            os.replace(temp_sidecar,sidecar)
        finally:
            partial.unlink(missing_ok=True)
    return dict(ok=True,complete=manifest['complete'],archive=str(output),sha256=checksum,
                files=len(inventory),validation=validation,source_commit=commit)


def verify_archive(archive, require_sidecar=True, max_bytes=100*1024**3):
    archive = Path(archive).resolve()
    if require_sidecar:
        sidecar = Path(str(archive)+'.sha256')
        if not sidecar.is_file():
            raise ValueError('缺少 .zip.sha256；可能尚未同步完成，請等待或一併下載')
        parts = sidecar.read_text(encoding='utf-8').split()
        if not parts:
            raise ValueError('校驗碼檔案為空，請等待同步完成')
        expected = parts[0]
        if len(expected)!=64 or sha(archive)!=expected:
            raise ValueError('ZIP 校驗失敗，請確認雲端同步完成')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();seen=set();total=0
        for info in infos:
            safe_name(info.filename)
            key=unicodedata.normalize('NFC',info.filename).casefold()
            if key in seen or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('資料包有重複路徑、目錄或連結：'+info.filename)
            seen.add(key);total+=info.file_size
        if total>max_bytes:
            raise ValueError('解壓總容量超出限制；請確認資料包大小')
        info=z.getinfo('TRANSFER-MANIFEST.json')
        if info.file_size>128*1024**2:
            raise ValueError('清單檔過大')
        manifest=json.loads(z.read(info))
        if manifest.get('schema_version')!=SCHEMA:
            raise ValueError('不支援的移交包版本')
        rows=manifest['files'];paths=[r['path'] for r in rows]
        if len(set(paths))!=len(paths) or set(paths)|{'TRANSFER-MANIFEST.json'}!={i.filename for i in infos} or 'TRANSFER-MANIFEST.json' in paths:
            raise ValueError('清單與實際檔案數不一致')
        path_set=set(paths)
        for path in paths:
            if any(str(parent) in path_set for parent in PurePosixPath(path).parents if str(parent) != '.'):
                raise ValueError('資料包檔案與父路徑衝突：'+path)
        for row in rows:
            safe_name(row['path']);info=z.getinfo(row['path'])
            if info.file_size!=row['bytes']:
                raise ValueError('檔案大小不符：'+row['path'])
            h=hashlib.sha256()
            with z.open(info) as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=row['sha256']:
                raise ValueError('檔案校驗失敗：'+row['path'])
        for m in manifest['mappings']:
            safe_name(m['relative'])
        return manifest


def relocate_database(path, mappings):
    """Update text paths/JSON only; preserve labels, keys, timestamps and states."""
    with closing(sqlite3.connect(path)) as con:
        tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            quote=lambda s:'"'+s.replace('"','""')+'"'
            columns=[r[1] for r in con.execute('PRAGMA table_info('+quote(table)+')')]
            try:
                rows=con.execute('SELECT rowid,* FROM '+quote(table)).fetchall()
            except sqlite3.OperationalError:
                raise ValueError('不支援無 rowid 的資料表：'+table)
            for row in rows:
                changes={}
                for key,value in zip(columns,row[1:]):
                    if isinstance(value,str):
                        new=rebase(value,mappings)
                        if value.startswith(('{','[')):
                            try:new=json.dumps(rebase(json.loads(value),mappings),ensure_ascii=False)
                            except ValueError:pass
                        if value!=new:changes[key]=new
                if changes:
                    con.execute('UPDATE '+quote(table)+' SET '+','.join(quote(k)+'=?' for k in changes)+' WHERE rowid=?',[*changes.values(),row[0]])
        con.commit()


def import_bundle(archive, destination, allow_incomplete=False):
    archive=Path(archive).expanduser().resolve();destination=Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('目的資料夾已存在；請用新名稱，匯入不覆寫既有紀錄')
    manifest=verify_archive(archive)
    if not manifest['complete'] and not allow_incomplete:
        raise ValueError('這是缺件備份，不能當正式完整移交；請回來源端補齊')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=destination.parent/('.'+destination.name+'.import-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        with zipfile.ZipFile(archive) as z:
            for row in manifest['files']:
                target=stage/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(row['path']) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
                if target.stat().st_size != row['bytes'] or sha(target) != row['sha256']:
                    raise ValueError('解壓時檔案校驗失敗：'+row['path'])
                if 'mtime_ns' in row:
                    os.utime(target,ns=(row['mtime_ns'],row['mtime_ns']))
        mappings=sorted([(m['old'],str(destination/m['relative'])) for m in manifest['mappings']],key=lambda p:-len(p[0]))
        old_source=manifest['source_acquisition'].get('source','')
        new_source=rebase(old_source,mappings)
        old_id=manifest['source_scope_id']
        new_id=(hashlib.sha256(os.path.normcase(os.path.abspath(new_source)).encode()).hexdigest()[:16] if new_source else 'local')
        if old_id != new_id:
            mappings.insert(0,('uploads/'+old_id,'uploads/'+new_id))
            mappings.insert(0,(str(destination/'workspace/data/uploads'/old_id),str(destination/'workspace/data/uploads'/new_id)))
        # Portable relative references are relative to the original install root.
        for path in stage.rglob('*.json'):
            if path.is_relative_to(stage/'models') or path.is_relative_to(stage/'handoff-history'):
                continue
            value=read(path)
            relocated=rebase(value,mappings)
            if value != relocated:
                write(path,relocated)
        for db in stage.rglob('*'):
            if db.suffix.lower() in ('.sqlite3','.sqlite','.db'):
                relocate_database(db,mappings)
        for name in ('data','outputs','state','reports','review'):
            (stage/'workspace'/name).mkdir(parents=True,exist_ok=True)
        config=stage/'config/station.json';settings=read(config)
        settings.update(workspace='../workspace',model_root='../models',default_provider='cpu',allow_cpu_fallback=True)
        settings['acquisition']=dict(settings.get('acquisition',{}),enabled=False)
        # Resolve relative references from folder-based portable editions.
        reference=settings.get('reference')
        if reference and not Path(reference).is_absolute():
            settings['reference']=str((destination/'config'/reference).resolve())
        write(config,settings)
        ui_file=stage/'workspace/state/ui_settings.json';ui=read(ui_file) if ui_file.exists() else {}
        ui['acquisition']=dict(ui.get('acquisition',manifest['source_acquisition']),enabled=False)
        ui.update(dino_execution='cpu',allow_cpu_fallback=True)
        for profile in ui.get('machine_profiles',[]):
            if not Path(profile['reference']).is_absolute():
                profile['reference']=str(destination/profile['reference'])
        write(ui_file,ui)
        # Keep upload visibility after the source path identity changes on the new OS.
        old_source=manifest['source_acquisition'].get('source','')
        new_source=ui['acquisition'].get('source','')
        if old_source and new_source:
            old_id=manifest['source_scope_id']
            new_id=hashlib.sha256(os.path.normcase(os.path.abspath(new_source)).encode()).hexdigest()[:16]
            uploads=stage/'workspace/data/uploads'
            if (uploads/old_id).exists() and old_id!=new_id:
                if (uploads/new_id).exists():raise ValueError('來源照片目錄識別衝突')
                (uploads/old_id).rename(uploads/new_id)
        write(stage/'TRANSFER-MANIFEST.json',manifest)
        write(stage/'IMPORT-RECEIPT.json',dict(schema_version=SCHEMA,imported_at=datetime.now(timezone.utc).isoformat(),
             archive=str(archive),archive_sha256=sha(archive),source_commit=manifest['source_commit'],
             source_dirty=manifest.get('source_dirty'),mappings=mappings,acquisition_disabled=True,
             note='原始資料包保留；只重定位路徑、設定 CPU、停用監看。未重跑檢測。'))
        # Validate references against staging while their stored paths target the final folder.
        final_ui=ui_file.read_bytes();write(ui_file,rebase(read(ui_file),[(str(destination),str(stage))]))
        validation=validate_station(stage)
        ui_file.write_bytes(final_ui)
        if not validation['ok'] and not allow_incomplete:
            raise ValueError('匯入後缺件：\n'+'\n'.join(validation['errors']))
        # Avoid overwrite races. A destination created during validation is not replaced.
        if destination.exists():raise ValueError('目的資料夾在匯入期間已建立')
        stage.rename(destination)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    return dict(ok=True,destination=str(destination),config=str(destination/'config/station.json'),
                source_commit=manifest['source_commit'],validation=validation,
                next_step='依操作說明，以此 config 啟動；確認來源後才開啟監看。')


def check_station(root,config=None):
    loc=layout(root,config)
    result=validate_station(loc['root'],work=loc['work'],models=loc['models'])
    acquisition=dict(loc['settings'].get('acquisition',{}),**loc['ui'].get('acquisition',{}))
    if acquisition.get('source') and not Path(acquisition['source']).is_dir():
        result['errors'].append('來源圖資無法讀取：'+acquisition['source'])
        result['ok']=False
    result['running_service']=active_server(loc['work'])
    result['workspace']=str(loc['work'])
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description='X-RAY Windows／Mac 私人資料移交（不重跑檢測）')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('check','export'):
        q=sub.add_parser(name);q.add_argument('--root',required=True);q.add_argument('--config')
        if name=='export':
            q.add_argument('--output',required=True);q.add_argument('--extra',action='append',default=[])
            q.add_argument('--allow-incomplete',action='store_true',help='僅作缺件備份，不能當正式移交')
            q.add_argument('--key-file',help='外部金鑰檔；指定後輸出 AES-GCM 加密包')
    q=sub.add_parser('verify');q.add_argument('archive');q.add_argument('--key-file')
    q=sub.add_parser('import');q.add_argument('archive');q.add_argument('--destination',required=True)
    q.add_argument('--allow-incomplete',action='store_true');q.add_argument('--key-file')
    q=sub.add_parser('init-key');q.add_argument('path')
    args=p.parse_args(argv)
    try:
        if args.command=='init-key':
            from transfer_crypto import create_key
            result=dict(ok=True,key_file=create_key(args.path),note='金鑰另行安全保存；不放 Git 或 Drive 資料包')
        elif args.command=='check':result=check_station(args.root,args.config)
        elif args.command=='export':
            if args.key_file:
                from transfer_crypto import export_encrypted
                result=export_encrypted(args.root,args.output,args.key_file,args.config,args.extra,args.allow_incomplete)
            else:result=export_bundle(args.root,args.output,args.config,args.extra,args.allow_incomplete)
        elif args.command=='verify':
            from transfer_crypto import open_bundle
            with open_bundle(args.archive,args.key_file) as plain:
                m=verify_archive(plain)
            result=dict(ok=True,complete=m['complete'],source_commit=m['source_commit'],files=len(m['files']),validation=m['validation'])
        else:
            if args.key_file:
                if args.allow_incomplete:raise ValueError('加密正式移交不接受缺件匯入')
                from transfer_crypto import import_encrypted
                result=import_encrypted(args.archive,args.destination,args.key_file)
            else:result=import_bundle(args.archive,args.destination,args.allow_incomplete)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['ok'] else 2
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,zipfile.BadZipFile) as e:
        print(json.dumps(dict(ok=False,error=str(e)),ensure_ascii=False,indent=2),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
