"""Private local r3 checkpoint; never uploads field data or encryption keys."""
from contextlib import closing
import hashlib,json,os,sqlite3,subprocess,tempfile,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/checkpoints/2026-11-05-dino-r3-rd-handoff'
TAG='checkpoint-2026-11-05-dino-r3-rd-handoff'
SKIP={'__pycache__','.git','node_modules','preview-browser','edge-profile','migration-fixture',
      'snapshot-partial-not-final'}
ARTIFACTS=['XRayReview-DINO-Optimized-r3-20261104-Windows-x64.zip',
           'XRay-RD-r3-Reproduction-20261105.zip','XRayTransfer-Windows-20261105.zip']

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    roots=[ROOT/p for p in ('models','config','data','outputs','state')]
    roots += [p for p in (ROOT/'workspace').iterdir() if p.is_dir() and p.name not in ('checkpoints','venvs','gpu-wheels')]
    files=[]
    for root in roots:
        if not root.exists():continue
        for folder,dirs,names in os.walk(root):
            dirs[:]=[n for n in dirs if n not in SKIP and not (Path(folder)/n).is_symlink()]
            for n in names:
                p=Path(folder)/n
                if p.is_symlink() or n.endswith(('-wal','-shm','.key','.pem')) or n in ('.env','id_rsa','id_ed25519'):continue
                files.append(p)
    public=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    files += [ROOT/p for p in public if p and (ROOT/p).is_file()]
    files += [p for name in ARTIFACTS for p in (ROOT/'dist'/name,ROOT/'dist'/(name+'.sha256'))]
    files=list(dict.fromkeys(files));inventory=[];archive=OUT/'snapshot.zip'
    print('Local checkpoint:',OUT,'files:',len(files),flush=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
        for i,p in enumerate(files,1):
            rel=p.relative_to(ROOT).as_posix();source=p;temporary=None;kind='exact_copy'
            if p.suffix.lower() in ('.sqlite3','.sqlite','.db'):
                fd,name=tempfile.mkstemp(suffix='.sqlite3',dir=OUT);os.close(fd);temporary=Path(name)
                with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(temporary)) as b:a.backup(b)
                source=temporary;kind='consistent_sqlite_snapshot'
            before=source.stat();h=hashlib.sha256()
            with source.open('rb') as a,z.open(rel,'w',force_zip64=True) as b:
                for block in iter(lambda:a.read(1024*1024),b''):h.update(block);b.write(block)
            after=source.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),rel
            inventory.append(dict(path=rel,bytes=after.st_size,sha256=h.hexdigest(),kind=kind))
            if temporary:temporary.unlink()
            if i%5000==0:print('Archived',i,'/',len(files),flush=True)
    with zipfile.ZipFile(archive) as z:
        for i,row in enumerate(inventory,1):
            h=hashlib.sha256()
            with z.open(row['path']) as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
            assert h.hexdigest()==row['sha256'],row['path']
            if i%10000==0:print('Verified',i,'/',len(inventory),flush=True)
    private=OUT/'private-inventory.json';private.write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(tag=TAG,branch='codex/next-development-20261103',files=len(inventory),bytes=sum(x['bytes'] for x in inventory),
        archive_sha256=sha(archive),inventory_sha256=sha(private),sqlite_snapshots=sum(x['kind']=='consistent_sqlite_snapshot' for x in inventory),
        every_entry_sha256_verified=True,detection_rerun=False,key_included=False,
        excluded=['prior checkpoints','Python environments/wheel caches','browser profiles','synthetic migration installation copies','private key files','external Pictures/X-Ray originals (kept in place)'])
    (OUT/'backup-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
