"""Read-only source polling, immutable local snapshots and restart-safe import queue."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
import subprocess
import sys
import cv2
import numpy as np
from runtime_paths import DATA, STATE, SETTINGS
from station_settings import acquisition_config, source_scope, in_source

SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}

def source_images(source):
    """Raise on incomplete directory reads: an offline folder is not an empty one."""
    with os.scandir(source) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                yield from source_images(Path(entry.path))
            elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in SUFFIXES:
                yield Path(entry.path)

class Importer:
    def __init__(self, config=None, data=DATA, state=STATE, analyze=None, recover=True):
        self.config = dict(config if config is not None else acquisition_config())
        self.data, self.state, self.analyze = Path(data), Path(state), analyze
        self.state.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state / 'acquisition.sqlite3'
        self.status = dict(state='disabled', error=None, last_scan=None)
        self.stop_event = threading.Event()
        self.scan_lock = threading.Lock()
        self.thread = None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS files (source TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, stable_since REAL, state TEXT, local TEXT, sha TEXT, error TEXT, acquired_at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events (local TEXT PRIMARY KEY, source TEXT, sha TEXT, acquired_at TEXT, state TEXT, error TEXT)')
            if 'present' not in {row[1] for row in db.execute('PRAGMA table_info(files)')}:
                db.execute('ALTER TABLE files ADD COLUMN present INTEGER NOT NULL DEFAULT 1')
            if recover:
                db.execute("UPDATE events SET state='pending' WHERE state='analyzing'")

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def scan_once(self, now=None):
        if not self.config.get('enabled', False):
            self.status.update(state='disabled'); return
        with self.scan_lock:
            now = time.time() if now is None else now
            source = Path(self.config['source'])
            if not source.is_dir():
                raise OSError('共享資料夾無法連線或無讀取權限')
            # Finish enumeration/stat before changing presence. Partial/failed scans
            # must retain the last complete inventory and all historical snapshots.
            inventory = [(path, path.stat()) for path in source_images(source)]
            seen = {str(path.absolute()) for path, _ in inventory}
            with self.connect() as db:
                for path, st in inventory:
                    if not path.resolve().is_relative_to(source.resolve()):
                        continue
                    key = str(path.absolute())
                    row = db.execute('SELECT size,mtime,stable_since,state FROM files WHERE source=?', (key,)).fetchone()
                    if row is None or row[:2] != (st.st_size, st.st_mtime_ns):
                        db.execute('INSERT OR REPLACE INTO files(source,size,mtime,stable_since,state) VALUES(?,?,?,?,?)',
                                   (key, st.st_size, st.st_mtime_ns, now, 'waiting'))
                        continue
                    db.execute('UPDATE files SET present=1 WHERE source=?', (key,))
                    if row[3] not in ('waiting', 'retry') or now-row[2] < float(self.config.get('stable_seconds',15)):
                        continue
                    local = self.data / 'incoming' / (uuid.uuid4().hex + path.suffix.lower())
                    local.parent.mkdir(parents=True, exist_ok=True)
                    partial = local.with_suffix(local.suffix + '.partial')
                    try:
                        # A bounded-size local snapshot; never modify the source.
                        limit = int(self.config.get('max_bytes', 100 * 1024 * 1024))
                        if st.st_size <= 0 or st.st_size > limit:
                            raise ValueError('來源檔案大小超出允許範圍')
                        sha = hashlib.sha256()
                        count = 0
                        with path.open('rb') as src, partial.open('wb') as dst:
                            while chunk := src.read(1024*1024):
                                count += len(chunk)
                                if count > limit: raise ValueError('來源檔案持續增長或過大')
                                sha.update(chunk); dst.write(chunk)
                        after = path.stat()
                        if (after.st_size, after.st_mtime_ns) != row[:2] or count != st.st_size:
                            raise ValueError('來源仍在寫入，稍後重試')
                        blob = partial.read_bytes()
                        decoded = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_UNCHANGED)
                        if decoded is None: raise ValueError('影像尚未完成或無法解碼')
                        if min(decoded.shape[:2]) < 128 or max(decoded.shape[:2]) > 16000:
                            raise ValueError('影像尺寸不符')
                        os.replace(partial, local)
                        acquired = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                        db.execute("INSERT INTO events VALUES(?,?,?,?,?,NULL)", (local.relative_to(self.data).as_posix(),key,sha.hexdigest(),acquired,'pending'))
                        db.execute("UPDATE files SET state='imported',local=?,sha=?,error=NULL,acquired_at=? WHERE source=?",
                                   (local.relative_to(self.data).as_posix(), sha.hexdigest(), time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()), key))
                        db.commit()
                    except (OSError, ValueError) as exc:
                        partial.unlink(missing_ok=True)
                        db.execute("UPDATE files SET state='retry',error=?,stable_since=? WHERE source=?", (str(exc), now, key))
                scope = source_scope(self.config)
                for (key,) in db.execute('SELECT source FROM files').fetchall():
                    if in_source(key, scope['path']) and key not in seen:
                        db.execute('UPDATE files SET present=0 WHERE source=?', (key,))
                db.commit()
            self.status.update(state='online', error=None, last_scan=now, source_id=source_scope(self.config)['id'])

    def process_pending(self):
        if self.analyze is None: return
        with self.connect() as db:
            rows = db.execute("SELECT e.source,e.local FROM events e JOIN files f ON f.source=e.source AND f.local=e.local WHERE f.present=1 AND e.state IN ('pending','analysis_error')").fetchall()
        for source, local in rows:
            config = acquisition_config() if self.thread else self.config
            if not in_source(source, source_scope(config)['path']):
                continue
            if self.stop_event.is_set() or self.thread and not acquisition_config().get('enabled',False): break
            with self.connect() as db:
                db.execute("UPDATE events SET state='analyzing' WHERE local=?", (local,))
            try:
                self.analyze(self.data / local, Path(source).name)
                state, error = 'done', None
            except Exception as exc:
                state, error = 'analysis_error', str(exc)
            with self.connect() as db:
                db.execute('UPDATE events SET state=?,error=? WHERE local=?', (state,error,local))

    def metadata(self, include_history=False):
        with self.connect() as db:
            query = ('SELECT local,source,acquired_at,state,error FROM events' if include_history else
                     'SELECT e.local,e.source,e.acquired_at,e.state,e.error FROM events e JOIN files f ON f.source=e.source AND f.local=e.local WHERE f.present=1')
            return {row[0]:dict(source_path=row[1], original_filename=Path(row[1]).name, acquired_at=row[2], state=row[3],error=row[4])
                    for row in db.execute(query)}

    def info(self):
        config = acquisition_config() if self.thread else self.config
        scope = source_scope(config)
        with self.connect() as db:
            files = db.execute('SELECT source,state FROM files WHERE present=1').fetchall()
            events = db.execute('SELECT e.source,e.state FROM events e JOIN files f ON f.source=e.source AND f.local=e.local WHERE f.present=1').fetchall()
        counts, event_counts = {}, {}
        for rows, target in ((files, counts), (events, event_counts)):
            for source, state in rows:
                if in_source(source, scope['path']):
                    target[state] = target.get(state, 0) + 1
        status = dict(self.status)
        # A successful scan of A does not imply that a newly selected B is online.
        if status.get('source_id') != scope['id'] and config.get('enabled',False):
            status.update(state='waiting',error=None,last_scan=None)
        return dict(status, source=scope, events=sum(event_counts.values()),
                    enabled=config.get('enabled',False), counts=counts, event_counts=event_counts)

    def isolated_scan(self):
        # SMB calls can block inside the OS: bound the complete scan with a killable process.
        command = [sys.executable, '--acquisition-scan'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve())]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                timeout=float(self.config.get('scan_timeout_seconds',30)),
                                env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
        if result.returncode:
            raise OSError(result.stderr.strip()[-1000:] or '取圖工作程序失敗')
        self.status.update(json.loads(result.stdout))

    def run(self):
        while not self.stop_event.is_set():
            self.config = acquisition_config()
            try:
                if self.config.get('enabled',False):
                    self.isolated_scan()
                else:
                    self.status.update(state='disabled',error=None)
            except Exception as exc:
                self.status.update(state='offline',error=str(exc))
            try:
                if self.config.get('enabled',False):
                    self.process_pending()
            except Exception as exc:
                self.status.update(error=str(exc))
            self.stop_event.wait(max(1,float(self.config.get('poll_seconds',3))))

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.thread = threading.Thread(target=self.run,daemon=True,name='xray-acquisition')
        self.thread.start()

def scan_worker():
    worker = Importer(recover=False)
    try:
        worker.scan_once()
        print(json.dumps(worker.status, ensure_ascii=False))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__': scan_worker()
