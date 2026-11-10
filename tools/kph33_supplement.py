"""Create and restore a KPH33 evidence supplement, independent of station backups."""
import argparse,hashlib,json,os,shutil,tempfile,zipfile
from pathlib import Path, PurePosixPath
import transfer_crypto as crypto
import transfer_parts as parts

BLOCK=1024*1024

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(BLOCK),b''):h.update(b)
 return h.hexdigest()

def collect(evaluation,source):
 e=Path(evaluation).resolve();s=Path(source).resolve(); files={}
 def add(path,name):
  p=Path(path)
  if p.is_symlink() or not p.is_file():raise ValueError('Missing or symlink input: '+str(p))
  if name in files:raise ValueError('Duplicate path: '+name)
  files[name]=p
 for sub in ('report','audit'):
  for p in sorted((e/sub).rglob('*')):
   if p.is_file():add(p,'evaluation/'+p.relative_to(e).as_posix())
 for p in sorted(e.glob('*.json')):add(p,'evaluation/'+p.name)
 for method in ('r3','4r'):
  for folder in sorted((e/'runs'/method).iterdir()):
   if folder.is_dir():
    for name in ('result.json','complete.json','reference.png','aligned.png','all_overlay.png'):
     add(folder/name,'evaluation/runs/'+method+'/'+folder.name+'/'+name)
 for sub in ('Golden','Answer','待測'):
  for p in sorted((s/sub).glob('*.tiff')):add(p,'source/'+sub+'/'+p.name)
 assert len(list((s/'Golden').glob('*.tiff')))==1
 assert len(list((s/'Answer').glob('*.tiff')))==10
 assert len(list((s/'待測').glob('*.tiff')))==10
 assert len(list((e/'report').glob('*.html')))==24
 return files

def build(evaluation,source,output,key):
 output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
 files=collect(evaluation,source);inventory=[dict(path=n,bytes=p.stat().st_size,sha256=sha(p)) for n,p in files.items()]
 before={x['path']:x['sha256'] for x in inventory}
 manifest=dict(format='KPH33-evidence-supplement-v2',description='Supplement only; requires prior lean 4r package for models and reference bank; no station settings or key',files=inventory)
 with tempfile.TemporaryDirectory(prefix='xray-kph33-build-') as temp:
  plain=Path(temp)/'supplement.zip'
  with zipfile.ZipFile(plain,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
   z.writestr('SUPPLEMENT-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
   written=set()
   for name,p in files.items():
    digest=before[name]
    if digest not in written:z.write(p,'blobs/'+digest);written.add(digest)
  if any(sha(p)!=before[n] for n,p in files.items()):raise ValueError('Source changed during build')
  crypto.encrypt_file(plain,output,key)
 part=parts.split_file(output,output.parent/'parts',96*1024*1024)
 print(json.dumps(dict(files=len(files),source_bytes=sum(x['bytes'] for x in inventory),encrypted_bytes=output.stat().st_size,sha256=sha(output),parts=part),ensure_ascii=False),flush=True)

def restore(archive,key,destination):
 archive=Path(archive).resolve();destination=Path(destination).resolve()
 if destination.exists():raise ValueError('Destination already exists')
 destination.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='xray-kph33-import-',dir=destination.parent) as temp:
  temp=Path(temp);plain=temp/'supplement.zip';crypto.decrypt_file(archive,plain,key)
  stage=temp/'isolated';stage.mkdir()
  with zipfile.ZipFile(plain) as z:
   names=z.namelist()
   if len(names)!=len(set(names)):raise ValueError('Duplicate zip entries')
   manifest=json.loads(z.read('SUPPLEMENT-MANIFEST.json'))
   if manifest.get('format') not in ('KPH33-evidence-supplement-v2','XRAY-4R-REFERENCE-SUPPLEMENT-v1'):raise ValueError('Wrong supplement format')
   rows=manifest['files'];paths=[r['path'] for r in rows]
   if set(names)!={'SUPPLEMENT-MANIFEST.json',*('blobs/'+r['sha256'] for r in rows)} or len(paths)!=len(set(paths)) or len(paths)!=len({p.casefold() for p in paths}):raise ValueError('Inventory mismatch')
   for row in rows:
    name=row['path'];q=PurePosixPath(name)
    if q.is_absolute() or '..' in q.parts or '\\' in name or ':' in name or not q.parts:raise ValueError('Unsafe archive path')
    p=stage.joinpath(*q.parts);p.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();size=0
    with z.open('blobs/'+row['sha256']) as src,p.open('xb') as dst:
     for b in iter(lambda:src.read(BLOCK),b''):dst.write(b);h.update(b);size+=len(b)
    if size!=row['bytes'] or h.hexdigest()!=row['sha256']:raise ValueError('File verification failed: '+name)
   (stage/'SUPPLEMENT-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
  os.rename(stage,destination)
 return dict(ok=True,files=len(rows),archive_sha256=sha(archive),isolated_restore=str(destination),supplement_only=True)

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 b=sub.add_parser('build');b.add_argument('--evaluation',required=True);b.add_argument('--source',required=True);b.add_argument('--output',required=True);b.add_argument('--key-file',required=True)
 r=sub.add_parser('restore');r.add_argument('archive');r.add_argument('--key-file',required=True);r.add_argument('--destination',required=True)
 a=p.parse_args()
 if a.command=='build':build(a.evaluation,a.source,a.output,a.key_file)
 else:print(json.dumps(restore(a.archive,a.key_file,a.destination),ensure_ascii=False))
if __name__=='__main__':main()
