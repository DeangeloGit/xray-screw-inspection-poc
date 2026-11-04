"""Current-folder inventory excludes removed/replaced snapshots, keeps history."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image

def checks(root):
    os.environ['XRAY_WORKSPACE']=str(root/'workspace')
    os.environ['XRAY_CONFIG']=str(root/'absent-station.json')
    from acquisition import Importer
    source=root/'source';source.mkdir();data=root/'workspace/data';state=root/'workspace/state'
    for n in range(5):Image.new('L',(128,128),20+n*30).save(source/f'{n}.png')
    worker=Importer(dict(enabled=True,source=str(source),stable_seconds=0),data=data,state=state)
    worker.scan_once(now=0);worker.scan_once(now=1)
    assert len(worker.metadata())==5
    original={p:p.read_bytes() for p in (data/'incoming').glob('*.png')}
    removed={p:(p.read_bytes(),p.stat()) for p in [source/'0.png',source/'1.png']}
    for p in removed:p.unlink()
    worker.scan_once(now=2)
    assert len(worker.metadata())==3,'removed originals must disappear from the current list'
    assert len(worker.metadata(include_history=True))==5,'historical events must remain'
    assert worker.info()['events']==3
    calls=[];worker.analyze=lambda path,name:calls.append(name);worker.process_pending()
    assert set(calls)=={'2.png','3.png','4.png'},'do not analyze removed originals'
    for p,(blob,st) in removed.items():
        p.write_bytes(blob);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
    worker.scan_once(now=3)
    assert len(worker.metadata())==5 and len(worker.metadata(include_history=True))==5,'restoring unchanged originals must reuse history'
    Image.new('L',(128,128),240).save(source/'2.png')
    worker.scan_once(now=4)
    assert len(worker.metadata())==4,'old file version must not show while replacement is stabilizing'
    worker.scan_once(now=5)
    assert len(worker.metadata())==5 and len(worker.metadata(include_history=True))==6
    current=worker.metadata()
    (source/'0.png').unlink()
    def incomplete(_):
        yield source/'1.png'
        raise OSError('simulated unreadable subdirectory')
    with patch('acquisition.source_images',incomplete):
        try:worker.scan_once(now=6)
        except OSError:pass
        else:raise AssertionError('incomplete inventory must raise')
    assert worker.metadata()==current,'incomplete scan must not clear prior inventory'
    source.rename(root/'disconnected')
    try:worker.scan_once(now=7)
    except OSError:pass
    else:raise AssertionError('offline source must raise')
    assert worker.metadata()==current,'offline source must not be treated as empty'
    for p,blob in original.items():assert p.read_bytes()==blob,'snapshot modified or deleted'
    print('PASS: deleted files hidden, unchanged restoration reuses history, replacements show latest only, deleted pending work skipped, failed/offline scans preserve inventory, all old snapshots unchanged')

if __name__=='__main__':
    with TemporaryDirectory() as folder:
        checks(Path(folder).resolve())
        # sqlite3's transaction context manager does not close connections.
        import gc
        gc.collect()
