"""Private local checkpoint only. Never stage this snapshot's field data in Git."""
import sys,json,os,shutil,hashlib,sqlite3,subprocess,time,zipfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/checkpoints/2026-11-04-dino-performance-research'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    OUT.mkdir(parents=True,exist_ok=True);inventory=[]
    roots=[ROOT/'models',ROOT/'config',ROOT/'data',ROOT/'outputs',ROOT/'state']
    roots += [p for p in (ROOT/'workspace').iterdir() if p.is_dir() and p.name not in ('checkpoints','venvs','gpu-wheels')]
    files=[]
    for root in roots:
        if not root.exists():continue
        for folder,dirs,names in os.walk(root):
            dirs[:]=[n for n in dirs if n not in ('__pycache__','preview-browser','.git','node_modules')]
            for n in names:
                p=Path(folder)/n
                if n.endswith(('-wal','-shm')):continue
                if not p.is_symlink():files.append(p)
    public=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    files += [ROOT/p for p in public if p and (ROOT/p).is_file()]
    # Preserve the unchanged r2 deliveries as historical artifacts, not a new build.
    files += list((ROOT/'dist').glob('XRayReview-DINO-Paired-20261103-r2-*.zip*'))
    archive=OUT/'snapshot.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        for i,p in enumerate(dict.fromkeys(files),1):
            rel=p.relative_to(ROOT);kind='exact_copy';temporary=None;source_path=p
            if p.suffix.lower() in ('.sqlite3','.sqlite','.db'):
                fd,name=tempfile.mkstemp(suffix='.sqlite3',dir=OUT);os.close(fd);temporary=Path(name)
                with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as source:
                    with sqlite3.connect(temporary) as target:source.backup(target)
                source_path=temporary;kind='consistent_sqlite_snapshot'
            before=source_path.stat();h=hashlib.sha256()
            with source_path.open('rb') as src,z.open(rel.as_posix(),'w',force_zip64=True) as dest:
                for block in iter(lambda:src.read(1024*1024),b''):h.update(block);dest.write(block)
            after=source_path.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),str(p)
            inventory.append(dict(path=rel.as_posix(),bytes=after.st_size,sha256=h.hexdigest(),kind=kind))
            if temporary:temporary.unlink()
            if i%5000==0:print(f'Archived {i}/{len(files)} files',flush=True)
    with zipfile.ZipFile(archive) as z:
        for i,row in enumerate(inventory,1):
            h=hashlib.sha256()
            with z.open(row['path']) as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            assert h.hexdigest()==row['sha256'],row['path']
            if i%10000==0:print(f'Verified archive {i}/{len(inventory)} files',flush=True)
    private=OUT/'private-inventory.json';private.write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(tag='checkpoint-2026-11-04-dino-performance-research',branch='codex/next-development-20261103',base_commit='e154c35',
        files=len(inventory),bytes=sum(r['bytes'] for r in inventory),inventory_sha256=sha(private),
        sqlite_snapshots=sum(r['kind']=='consistent_sqlite_snapshot' for r in inventory),copy_verification=True,archive='snapshot.zip',archive_sha256=sha(archive),
        excluded=['Python environments','wheel caches','browser preview profiles','node_modules','external original Pictures/X-Ray folder (preserved in place)'],
        source_image_note='Field snapshots/reference and report images in project workspaces are copied; external originals are not modified.')
    (OUT/'backup-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
