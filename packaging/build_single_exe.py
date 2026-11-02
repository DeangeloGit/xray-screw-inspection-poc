"""Append an offline runtime ZIP to a Windows x64 extractor. No external installer."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
MINIZ=ROOT/'build/miniz'
MAGIC=b'XRAYSFX-00000001'


def prepare_miniz():
    lock=json.loads((ROOT/'packaging/miniz-source.json').read_text())
    MINIZ.mkdir(parents=True,exist_ok=True)
    for name,expected in lock['sha256'].items():
        path=MINIZ/name
        if not path.exists():
            data=urllib.request.urlopen(f"https://raw.githubusercontent.com/richgel999/miniz/{lock['commit']}/{name}").read()
            path.write_bytes(data)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,name
    (MINIZ/'miniz_export.h').write_text('#pragma once\n#define MINIZ_EXPORT\n')


def build():
    prepare_miniz()
    archive=ROOT/'dist/XRayReview-Windows-x64-CPU.zip'
    data=archive.read_bytes();digest=hashlib.sha256(data).hexdigest()
    (MINIZ/'sfx_bundle.h').write_text('#define XRAY_BUNDLE_ID L"cpu-'+digest[:16]+'"\n#define XRAY_BUNDLE_ROOT L"XRayReview-Windows-x64-CPU"\n')
    zig=ROOT/'build/windows-cache/zig/zig-aarch64-macos-0.17.0/zig'
    stub=ROOT/'build/windows-cache/XRayReview-SFX-stub.exe'
    command=[str(zig),'cc','-target','x86_64-windows-gnu','-Os','-s','-municode',
             '-DMINIZ_NO_ARCHIVE_WRITING_APIS','-I'+str(MINIZ),str(ROOT/'packaging/windows_sfx.c'),
             *[str(MINIZ/name) for name in ('miniz.c','miniz_zip.c','miniz_tinfl.c','miniz_tdef.c')],
             '-lshell32','-luser32','-o',str(stub)]
    subprocess.run(command,check=True)
    output=ROOT/'dist/XRayReview-CPU-Standalone.exe'
    with output.open('wb') as stream:
        stream.write(stub.read_bytes());stream.write(data);stream.write(MAGIC);stream.write(struct.pack('<Q',len(data)))
    full_digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.exe.sha256').write_text(full_digest+'  '+output.name+'\n')
    output.with_suffix('.build.json').write_text(json.dumps(dict(
        architecture='Windows x64',bundle_id='cpu-'+digest[:16],payload_sha256=digest,
        exe_sha256=full_digest,payload_bytes=len(data),windows_execution_verified=False,
        extractor_source=lock_source(),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),indent=2))
    print(json.dumps(dict(file=str(output),bytes=output.stat().st_size,sha256=full_digest),indent=2),flush=True)
    return output


def lock_source():return json.loads((ROOT/'packaging/miniz-source.json').read_text())['commit']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if args.prepare_only:prepare_miniz()
    else:build()
