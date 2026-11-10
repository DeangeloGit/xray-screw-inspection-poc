"""Build a small encrypted supplement of 4r reference images and feature banks."""
import argparse,hashlib,json,os,sys,tempfile,zipfile
from pathlib import Path
import transfer_crypto as crypto

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--asset-root',type=Path,required=True);p.add_argument('--home',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True);a=p.parse_args()
 root=a.asset_root.resolve();home=a.home.resolve();output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
 active=json.loads((home/'example-versions/active.json').read_text(encoding='utf8'))['version'];files={}
 def add(p,name):
  p=Path(p)
  if not p.is_file() or p.is_symlink() or name in files:raise ValueError('Missing, linked or duplicate input: '+name)
  files[name]=p
 names=['dino-4r-integrated-bank-20261106/curated_v5_review-bank.npz','dino-4r-visible-screw-20261106/visible-part-bank.npz','dino-4r-visible-screw-20261106/v3/experiment-plan.json','dino-4r-example-audit-20261106/letterbox-112-bank.npz','dino-4r-connector-20261106/normal-connector-bank.npz']
 for name in names:add(root/'workspace'/name,'workspace/'+name)
 collection=root/'workspace/dino-4r-integrated-bank-20261106/active-reference-collection'
 for f in sorted(collection.rglob('*')):
  if f.is_file():add(f,'workspace/dino-4r-integrated-bank-20261106/active-reference-collection/'+f.relative_to(collection).as_posix())
 versions=home/'example-versions';add(versions/'active.json','example-home/example-versions/active.json')
 for v in sorted(versions.glob('4r-example-*')):
  if v.is_dir():
   for f in sorted(v.rglob('*')):
    if f.is_file():add(f,'example-home/example-versions/'+v.name+'/'+f.relative_to(v).as_posix())
 if active!='4r-curated-v5-review' and not (versions/active/'version.json').is_file():raise ValueError('目前啟用的範例版本不存在')
 inventory=[dict(path=n,bytes=f.stat().st_size,sha256=sha(f)) for n,f in files.items()]
 manifest=dict(format='XRAY-4R-REFERENCE-SUPPLEMENT-v1',description='4r reference images and feature banks; requires prior Lean DINO model; not a full station',active_version=active,files=inventory)
 with tempfile.TemporaryDirectory(prefix='xray-4r-refs-') as t:
  plain=Path(t)/'reference.zip'
  with zipfile.ZipFile(plain,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
   z.writestr('SUPPLEMENT-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2));written=set()
   for row in inventory:
    if row['sha256'] not in written:z.write(files[row['path']],'blobs/'+row['sha256']);written.add(row['sha256'])
  if any(sha(files[r['path']])!=r['sha256'] for r in inventory):raise ValueError('圖庫建立期間發生變更，請重新匯出')
  if json.loads((versions/'active.json').read_text(encoding='utf8'))['version']!=active:raise ValueError('圖庫版本建立期間變更')
  crypto.encrypt_file(plain,output,a.key_file)
 print(json.dumps(dict(ok=True,files=len(inventory),source_bytes=sum(r['bytes'] for r in inventory),encrypted_bytes=output.stat().st_size,sha256=sha(output),active_version=active),ensure_ascii=False))
if __name__=='__main__':main()
