"""Streaming authenticated encryption for X-RAY handoffs; keys stay external."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import uuid

import station_transfer as transfer

MAGIC=b'XRAYENC1'
HEADER_BYTES=8+16+12


def key_bytes(path):
    data=Path(path).expanduser().read_bytes()
    if len(data)!=32:raise ValueError('移交金鑰必須是獨立保存的 32 bytes 隨機檔案')
    return data


def create_key(path):
    path=Path(path).expanduser().resolve();path.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(os.urandom(32))
    return str(path)


def cipher(key,salt,nonce,tag=None):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    derived=hashlib.scrypt(key,salt=salt,n=16384,r=8,p=1,dklen=32)
    return Cipher(algorithms.AES(derived),modes.GCM(nonce,tag))


def encrypt_file(source,destination,keyfile):
    destination=Path(destination).resolve()
    if destination.exists() or Path(str(destination)+'.sha256').exists():raise ValueError('加密移交包已存在，請使用新名稱')
    destination.parent.mkdir(parents=True,exist_ok=True)
    salt,nonce=os.urandom(16),os.urandom(12);header=MAGIC+salt+nonce
    enc=cipher(key_bytes(keyfile),salt,nonce).encryptor();enc.authenticate_additional_data(header)
    partial=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        with Path(source).open('rb') as src,partial.open('xb') as dst:
            dst.write(header)
            for block in iter(lambda:src.read(1024*1024),b''):dst.write(enc.update(block))
            dst.write(enc.finalize());dst.write(enc.tag)
        os.replace(partial,destination)
        checksum=transfer.sha(destination)
        sidecar=Path(str(destination)+'.sha256');temp=sidecar.with_name(sidecar.name+'.partial')
        temp.write_text(checksum+'  '+destination.name+'\n',encoding='utf-8');os.replace(temp,sidecar)
    finally:partial.unlink(missing_ok=True)
    return checksum


def decrypt_file(source,destination,keyfile):
    source,destination=Path(source),Path(destination)
    if destination.exists():raise ValueError('解密目的檔已存在')
    partial=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.partial')
    from cryptography.exceptions import InvalidTag
    try:
        with source.open('rb') as src:
            header=src.read(HEADER_BYTES)
            if len(header)!=HEADER_BYTES or header[:8]!=MAGIC or source.stat().st_size<HEADER_BYTES+16:raise ValueError('不是支援的 X-RAY 加密移交包')
            src.seek(-16,os.SEEK_END);tag=src.read(16);src.seek(HEADER_BYTES)
            dec=cipher(key_bytes(keyfile),header[8:24],header[24:36],tag).decryptor();dec.authenticate_additional_data(header)
            remaining=source.stat().st_size-HEADER_BYTES-16
            with partial.open('xb') as dst:
                while remaining:
                    block=src.read(min(1024*1024,remaining))
                    if not block:raise ValueError('加密包未下載完整')
                    remaining-=len(block);dst.write(dec.update(block))
                dst.write(dec.finalize())
        os.replace(partial,destination)
    except InvalidTag as e:raise ValueError('加密認證失敗：金鑰不符或資料已損毀') from e
    finally:partial.unlink(missing_ok=True)


@contextmanager
def open_bundle(archive,keyfile=None):
    archive=Path(archive).expanduser().resolve()
    with archive.open('rb') as f:encrypted=f.read(8)==MAGIC
    if not encrypted:
        yield archive
        return
    if not keyfile:raise ValueError('加密移交需要外部金鑰檔；金鑰不放在 Google Drive 資料包內')
    sidecar=Path(str(archive)+'.sha256')
    if not sidecar.is_file():raise ValueError('缺少加密包 .sha256，請確認同步完成')
    parts=sidecar.read_text(encoding='utf-8').split()
    if not parts or transfer.sha(archive)!=parts[0]:raise ValueError('加密包校驗失敗')
    with tempfile.TemporaryDirectory(prefix='xray-decrypt-') as temp:
        plain=Path(temp)/'handoff.zip';decrypt_file(archive,plain,keyfile)
        transfer.verify_archive(plain,require_sidecar=False)
        Path(str(plain)+'.sha256').write_text(transfer.sha(plain)+'  handoff.zip',encoding='utf-8')
        yield plain


def export_encrypted(root,output,keyfile,config=None,extra=(),allow_incomplete=False):
    key=Path(keyfile).expanduser().resolve();key_bytes(key)
    loc=transfer.layout(root,config);files,mappings,_=transfer.collect(loc,extra)
    if key in {p.resolve() for p in files.values()}:
        raise ValueError('金鑰位於匯出範圍，請移至專案與圖資以外')
    output=Path(output).expanduser().resolve()
    if any(output.is_relative_to(Path(m['old'])) for m in mappings):
        raise ValueError('加密包不可存入匯出資料範圍')
    with tempfile.TemporaryDirectory(prefix='xray-encrypted-export-') as temp:
        plain=Path(temp)/'handoff.zip'
        result=transfer.export_bundle(root,plain,config,extra,allow_incomplete)
        checksum=encrypt_file(plain,output,keyfile)
        # Authenticate/decrypt the actual output before calling the local handoff valid.
        with open_bundle(output,keyfile) as check:transfer.verify_archive(check)
    return dict(result,archive=str(output),sha256=checksum,encrypted=True,local_decrypt_verified=True,cloud_verified=False)


def import_encrypted(archive,destination,keyfile):
    archive=Path(archive).expanduser().resolve()
    with archive.open('rb') as f:
        if f.read(8) != MAGIC:raise ValueError('此匯入流程只接受加密移交包')
    with open_bundle(archive,keyfile) as plain:
        result=transfer.import_bundle(plain,destination)
    receipt=Path(destination)/'IMPORT-RECEIPT.json';value=transfer.read(receipt)
    value.update(archive=str(archive),archive_sha256=transfer.sha(archive),encrypted=True)
    transfer.write(receipt,value)
    return result
