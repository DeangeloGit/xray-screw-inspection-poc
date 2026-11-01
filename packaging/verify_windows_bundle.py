"""Static checks only. These cannot establish successful Windows execution."""
import argparse
import email
import hashlib
import json
from pathlib import Path
import zipfile
import pefile
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

SYSTEM=set('advapi32 bcrypt bcryptprimitives cfgmgr32 comctl32 comdlg32 crypt32 cryptbase cryptsp dbghelp dhcpcsvc dnsapi dwmapi gdi32 hid imagehlp imm32 iphlpapi kernel32 kernelbase msimg32 mswsock msvcrt ncrypt netapi32 normaliz ntdll ole32 oleaut32 powrprof propsys psapi rpcrt4 secur32 setupapi shell32 shlwapi user32 userenv usp10 uxtheme version win32u windowscodecs winhttp wininet winmm winspool wintrust ws2_32 wtsapi32 ucrtbase shcore avrt d3d11 d3d12 d3dcompiler_47 dxgi opengl32 glu32 pdh'.split())
CUDA_PREFIXES=('cublas','cudart','cudnn','cufft','curand','nvrtc','nvcuda','nvjitlink','cudacompute','nvml')

def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'BUILD-MANIFEST.json').read_text(encoding='utf-8'))
    for name,expected in manifest['file_sha256'].items():
        path=root/name
        assert path.is_file(),name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,name
    binaries=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll','.pyd','.exe') and 'prerequisites' not in p.parts]
    names={p.name.lower() for p in binaries}
    unresolved=set(); optional=set(); tensorrt=set(); count=0
    for path in binaries:
        pe=pefile.PE(str(path),fast_load=True)
        assert pe.FILE_HEADER.Machine==0x8664,(str(path),hex(pe.FILE_HEADER.Machine))
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        for entry in [*getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]),*getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[])]:
            name=entry.dll.decode().lower()
            stem=name.removesuffix('.dll')
            if name in names or stem in SYSTEM or name.startswith(('api-ms-','ext-ms-')): continue
            if 'tensorrt' in path.name.lower() and name.startswith(('nvinfer','nvonnxparser')):tensorrt.add(name)
            elif name.startswith(CUDA_PREFIXES):optional.add(name)
            else:unresolved.add(name)
        pe.close(); count+=1
    site=root/'runtime/Lib/site-packages'
    installed={}
    metadata=[]
    for path in site.glob('*.dist-info/METADATA'):
        item=email.message_from_bytes(path.read_bytes()); metadata.append(item)
        installed[canonicalize_name(item['Name'])]=Version(item['Version'])
    environment=dict(implementation_name='cpython',implementation_version='3.14.10',os_name='nt',platform_machine='AMD64',
                     platform_release='11',platform_system='Windows',platform_version='10.0',python_full_version='3.14.10',
                     platform_python_implementation='CPython',python_version='3.14',sys_platform='win32',extra='')
    for item in metadata:
        for value in item.get_all('Requires-Dist',[]):
            req=Requirement(value)
            if req.marker and not req.marker.evaluate(environment):continue
            assert canonicalize_name(req.name) in installed,(item['Name'],str(req))
            assert installed[canonicalize_name(req.name)] in req.specifier,(item['Name'],str(req))
    assert (root/'runtime/python314._pth').read_text().splitlines()==['python314.zip','.','Lib/site-packages','../_app','import site']
    assert 'onnxruntime' in installed or 'onnxruntime-gpu' in installed
    archive=root.with_suffix('.zip')
    if archive.is_file():
        with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    report=dict(variant=manifest['variant'],binaries_verified=count,packages_verified=len(installed),
                missing_non_system_dlls=sorted(unresolved),external_cuda_dlls=sorted(optional),unused_tensorrt_dlls=sorted(tensorrt),
                windows_execution_verified=False)
    (root.parent/(root.name+'-static-check.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    assert not unresolved,'Missing DLLs: '+str(unresolved)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');verify(p.parse_args().folder)
