"""Fetch pinned official inputs; extract app-local MSVC DLLs without running installers."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'build/windows-cache'
DOWNLOADS=[
 ('https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip','python-3.14.10-embed-amd64.zip','90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'),
 ('https://ziglang.org/download/0.17.0/zig-aarch64-macos-0.17.0.tar.xz','zig.tar.xz','b607e9b9234790a008116ae5bdb71c6243b84b9fb42a53a9e70fde41c06c536a'),
 ('https://aka.ms/vc14/vc_redist.x64.exe','VC_redist.x64.exe','843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c')]


def download(item):
    url,name,expected=item
    path=CACHE/name
    if not path.exists():urllib.request.urlretrieve(url,path)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:raise ValueError(f'{name}: expected {expected}, got {actual}; do not use unverified input')
    print('Verified '+name,flush=True)


def prepare():
    CACHE.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(download,DOWNLOADS))
    if not (CACHE/'zig/zig-aarch64-macos-0.17.0/zig').exists():
        with tarfile.open(CACHE/'zig.tar.xz') as archive:archive.extractall(CACHE/'zig',filter='data')
    payload=(CACHE/'VC_redist.x64.exe').read_bytes(); start=0; containers=[]
    while True:
        pos=payload.find(b'MSCF',start)
        if pos<0:break
        start=pos+4
        if pos+36>len(payload):continue
        size=struct.unpack_from('<I',payload,pos+8)[0]
        if size<36 or pos+size>len(payload) or payload[pos+24:pos+26]!=b'\x03\x01':continue
        path=CACHE/f'vc-container-{len(containers)}.cab';path.write_bytes(payload[pos:pos+size]);containers.append(path)
    assert len(containers)==2
    vc_payload=CACHE/'vc-payload'; vc_payload.mkdir(exist_ok=True)
    subprocess.run(['bsdtar','-xf',str(containers[1]),'-C',str(vc_payload)],check=True)
    destination=CACHE/'vc-runtime'; destination.mkdir(exist_ok=True)
    subprocess.run(['bsdtar','-xf',str(vc_payload/'a4'),'-C',str(destination)],check=True)
    assert (destination/'msvcp140.dll_amd64').exists()
    for variant in ('cpu','gpu'):
        command=[sys.executable,'-m','pip','download','--dest',str(CACHE/('wheels-'+variant)),
                 '--platform','win_amd64','--python-version','3.14','--implementation','cp','--abi','cp314',
                 '--only-binary=:all:','-r',str(ROOT/'requirements.txt'),'colorama==0.4.6',
                 ('onnxruntime' if variant=='cpu' else 'onnxruntime-gpu')+'==1.31.1']
        subprocess.run(command,check=True)
    (CACHE/'download-sources.json').write_text(json.dumps([dict(url=u,file=n,sha256=h) for u,n,h in DOWNLOADS],indent=2),encoding='utf-8')

if __name__=='__main__':prepare()
