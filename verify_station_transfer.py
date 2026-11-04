"""Handoff roundtrip, independent integrity failures and cross-platform relocation."""
from contextlib import closing
import hashlib
import importlib.util
import json
import os
import ntpath
from pathlib import Path
import sqlite3
import tempfile
import zipfile
import sys
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('transfer',Path(__file__).parent/'tools/station_transfer.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
sys.path.insert(0,str(Path(__file__).parent/'tools'))
import transfer_crypto as crypto
import transfer_cloud as cloud


def fixture(root):
    for name in ('data','outputs','state','reports'):(root/name).mkdir(parents=True)
    (root/'data/ok_0.png').write_bytes(b'reference')
    source=root.parent/'external-originals';source.mkdir();(source/'zero-candidates.png').write_bytes(b'original')
    ref=root/'state/machine-references/mpt10.png';ref.parent.mkdir();ref.write_bytes(b'machine reference')
    t.write(root/'state/ui_settings.json',dict(machine_profiles=[dict(id='mpt10',name='MPT10',reference=str(ref))],selected_machine='mpt10',acquisition=dict(source=str(source),enabled=True),dino_execution='gpu'))
    model=root/'models/dino-paired';model.mkdir(parents=True);(model/'model.onnx').write_bytes(b'test-only-not-real-onnx')
    meta={};bank={}
    for label,count in [('screw',47),('normal',65)]:
        ids=[]
        for i in range(count):
            key=label+'-'+str(i);ids.append(key);file=model/'examples'/(key+'.png');file.parent.mkdir(exist_ok=True);file.write_bytes(key.encode())
            meta[key]=dict(file=file.name,sha256=t.sha(file))
        bank[label]=dict(ids=ids,embeddings=[[1.]+[0.]*383 for _ in ids])
    t.write(model/'examples.json',meta)
    t.write(model/'manifest.json',dict(schema_version=1,model_id='fixture',backend='dino_onnx',file='model.onnx',sha256=t.sha(model/'model.onnx'),decision_policy=t.POLICY,example_bank=bank,neighbors=3,decision_margin=0,input_size=[224,224],classes=['screw','non_screw']))
    t.write(root/'models/active.json',dict(schema_version=1,version_directory='dino-paired'))
    with closing(sqlite3.connect(root/'state/acquisition.sqlite3')) as db:
        db.execute('CREATE TABLE files(source TEXT PRIMARY KEY, local TEXT, state TEXT)')
        db.execute('INSERT INTO files VALUES(?,?,?)',(str(source/'zero-candidates.png'),'incoming/a.png','done'));db.commit()
    old_id=hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()[:16]
    upload=root/'data/uploads'/old_id/'u.png';upload.parent.mkdir(parents=True);upload.write_bytes(b'upload')
    t.write(root/'outputs/result.json',dict(filename='uploads/'+old_id+'/u.png',source_path=str(source/'zero-candidates.png'),human_reviews={'3':'screw'},image_review=dict(decision='screw',at='fixed'),candidates=[]))
    (root/'reports/index.html').write_text('<a href="image.png">full report</a>');(root/'reports/image.png').write_bytes(b'report asset')
    return source


def fails(task,word):
    try:task()
    except (ValueError,zipfile.BadZipFile) as e:
        assert word in str(e),(word,str(e))
    else:raise AssertionError('unexpected success: '+word)


def main():
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp).resolve();root=base/'station';root.mkdir();source=fixture(root)
        archive=base/'cloud/complete.zip';destination=base/'mac-import'
        with patch.object(t,'active_server',return_value=None):
            result=t.export_bundle(root,archive);assert result['complete']
        manifest=t.verify_archive(archive);assert any(r['path']=='external/source/zero-candidates.png' for r in manifest['files'])
        imported=t.import_bundle(archive,destination);assert imported['validation']['ok']
        ui=t.read(destination/'workspace/state/ui_settings.json')
        assert ui['dino_execution']=='cpu' and ui['acquisition']['enabled'] is False
        assert Path(ui['machine_profiles'][0]['reference']).is_file()
        assert Path(ui['acquisition']['source'])==destination/'external/source'
        assert t.sha(destination/'models/dino-paired/manifest.json')==t.sha(root/'models/dino-paired/manifest.json')
        result=t.read(destination/'workspace/outputs/result.json')
        assert result['human_reviews']=={'3':'screw'} and result['image_review']==dict(decision='screw',at='fixed')
        assert Path(result['source_path']).is_file()
        assert (destination/'workspace/data'/result['filename']).is_file()
        with closing(sqlite3.connect(destination/'workspace/state/acquisition.sqlite3')) as db:
            path,local,state=db.execute('SELECT * FROM files').fetchone();assert Path(path).is_file() and state=='done'
        assert (destination/'workspace/reports/image.png').read_bytes()==b'report asset'
        # Re-export an imported station and retain archived reports plus handoff history.
        with patch.object(t,'active_server',return_value=None):
            again=t.export_bundle(destination,base/'again.zip')
        second=t.import_bundle(base/'again.zip',base/'second')
        assert second['validation']['ok'] and list((base/'second/handoff-history').glob('*.json'))
        # Simulate bytes produced on a Windows workstation (drive-letter paths and scope ID).
        windows_stage=base/'windows-bytes';windows_stage.mkdir()
        with zipfile.ZipFile(archive) as z:z.extractall(windows_stage)
        wm=t.read(windows_stage/'TRANSFER-MANIFEST.json')
        old_source=wm['source_acquisition']['source'];old_id=wm['source_scope_id']
        conversions=[(str(root),r'C:\Station'),(str(source),r'Z:\Photos')]
        def win(v):
            if isinstance(v,dict):return {k:win(x) for k,x in v.items()}
            if isinstance(v,list):return [win(x) for x in v]
            if isinstance(v,str):
                for old,new in conversions:
                    if v==old or v.startswith(old+'/'):return new+v[len(old):].replace('/','\\')
            return v
        for path in windows_stage.rglob('*.json'):
            if path.name!='TRANSFER-MANIFEST.json' and not path.is_relative_to(windows_stage/'models'):t.write(path,win(t.read(path)))
        for mapping in wm['mappings']:mapping['old']=win(mapping['old'])
        wm['source_acquisition']=win(wm['source_acquisition'])
        win_id=hashlib.sha256(ntpath.normcase(r'Z:\Photos').encode()).hexdigest()[:16];wm['source_scope_id']=win_id
        (windows_stage/'workspace/data/uploads'/old_id).rename(windows_stage/'workspace/data/uploads'/win_id)
        output=windows_stage/'workspace/outputs/result.json';value=t.read(output);value['filename']=value['filename'].replace(old_id,win_id);t.write(output,value)
        with closing(sqlite3.connect(windows_stage/'workspace/state/acquisition.sqlite3')) as con:
            con.execute('UPDATE files SET source=?',(r'Z:\Photos\zero-candidates.png',));con.commit()
        wm['files']=[dict(path=p.relative_to(windows_stage).as_posix(),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=t.sha(p)) for p in windows_stage.rglob('*') if p.is_file() and p.name!='TRANSFER-MANIFEST.json']
        t.write(windows_stage/'TRANSFER-MANIFEST.json',wm)
        winzip=base/'windows.zip'
        with zipfile.ZipFile(winzip,'w') as z:
            for path in windows_stage.rglob('*'):
                if path.is_file():z.write(path,path.relative_to(windows_stage).as_posix())
        Path(str(winzip)+'.sha256').write_text(t.sha(winzip)+'  windows.zip')
        restored=t.import_bundle(winzip,base/'from-windows');assert restored['validation']['ok']
        wresult=t.read(base/'from-windows/workspace/outputs/result.json')
        assert Path(wresult['source_path']).is_file()
        assert (base/'from-windows/workspace/data'/wresult['filename']).is_file()
        fails(lambda:t.import_bundle(archive,destination),'已存在')
        with patch.object(t,'active_server',return_value='http://test'):
            fails(lambda:t.export_bundle(root,base/'running.zip'),'關閉')
        sidecar=Path(str(archive)+'.sha256');saved=sidecar.read_bytes();sidecar.unlink()
        fails(lambda:t.verify_archive(archive),'缺少');sidecar.write_bytes(saved)
        # Authenticated encryption, wrong keys and an isolated cloud-download replay.
        key=base/'outside.key';crypto.create_key(key)
        encrypted=base/'roundtrip.xray.enc'
        encrypted_result=crypto.export_encrypted(root,encrypted,key)
        assert encrypted_result['local_decrypt_verified'] and not encrypted_result['cloud_verified']
        encrypted_import=crypto.import_encrypted(encrypted,base/'encrypted-import',key)
        assert encrypted_import['validation']['ok']
        receipt=t.read(base/'encrypted-import/IMPORT-RECEIPT.json');assert receipt['archive']==str(encrypted)
        assert cloud.roundtrip(encrypted,encrypted,key)['isolated_restore_verified']
        wrong=base/'wrong.key';crypto.create_key(wrong)
        fails(lambda:crypto.decrypt_file(encrypted,base/'should-not-exist.zip',wrong),'認證失敗')
        assert not (base/'should-not-exist.zip').exists()
        damaged=base/'damaged.enc';payload=bytearray(encrypted.read_bytes());payload[-20]^=1;damaged.write_bytes(payload)
        fails(lambda:crypto.decrypt_file(damaged,base/'damaged.zip',key),'認證失敗')
        assert not (base/'damaged.zip').exists()
        # Missing one example blocks a full export; an explicit diagnostic backup is marked incomplete.
        (root/'models/dino-paired/examples/screw-0.png').unlink()
        with patch.object(t,'active_server',return_value=None):
            fails(lambda:t.export_bundle(root,base/'missing.zip'),'缺件')
            partial=t.export_bundle(root,base/'partial.zip',allow_incomplete=True);assert not partial['complete']
        fails(lambda:t.import_bundle(base/'partial.zip',base/'blocked'),'缺件備份')
        # Tampered bytes and traversal must not create any destination files.
        bad=base/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:
            z.writestr('../escape',b'bad')
        fails(lambda:t.verify_archive(bad,require_sidecar=False),'不安全')
        fails(lambda:t.safe_name('data/a?.png'),'不安全')
        fails(lambda:t.safe_name('data/CON.png'),'不安全')
        content=bytearray(archive.read_bytes());content[len(content)//2]^=1;archive.write_bytes(content)
        fails(lambda:t.verify_archive(archive),'校驗失敗')
        # Windows drive prefixes are replaced without interpreting them as Mac relative paths.
        assert t.rebase(r'D:\Station\state\ref.png',[(r'D:\Station',str(destination))])==str(destination/'state/ref.png')
        assert t.rebase(r'D:\Stationary\ref.png',[(r'D:\Station',str(destination))])==r'D:\Stationary\ref.png'
    with tempfile.TemporaryDirectory() as temp:
        import os, types
        import sys
        base=Path(temp).resolve();install=base/'install';install.mkdir();dest=base/'imported';dest.mkdir()
        config=dest/'config/station.json';t.write(config,{'workspace':'../workspace'})
        entry_spec=importlib.util.spec_from_file_location('frozen_entry',Path(__file__).parent/'packaging/frozen_entry.py')
        entry=importlib.util.module_from_spec(entry_spec);entry_spec.loader.exec_module(entry)
        fake_launch=types.SimpleNamespace(bind_server=lambda app,ports:None,main=lambda:None)
        previous=Path.cwd()
        try:
            with patch.dict(os.environ,{'XRAY_HANDOFF_CONFIG':str(config)}),patch.object(sys,'executable',str(install/'XRayReview.exe')),patch.object(sys,'argv',['XRayReview.exe']),patch.dict(sys.modules,{'launch':fake_launch}):
                assert entry.main()==0
                assert os.environ['XRAY_CONFIG']==str(config)
                assert os.environ['XRAY_WORKSPACE']==str(dest/'workspace')
        finally:os.chdir(previous)
    print('PASS: complete roundtrip, private model contract, labels/history, source/reference/SQLite relocation, missing examples, busy service, incomplete backup, checksum, traversal and no-overwrite')


if __name__=='__main__':main()
