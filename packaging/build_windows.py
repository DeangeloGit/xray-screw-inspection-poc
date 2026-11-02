"""Assemble an app-local Windows runtime from official, target-specific binary packages.

Run from the repository after populating build/windows-cache (see WINDOWS_BUILD.md).
This does not run PyInstaller or claim that Windows binaries were executed on macOS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'build/windows-cache'
SOURCES=['app.py','acquisition.py','detector.py','library.py','model_manager.py','reports.py','review_workflow.py',
         'runtime_paths.py','machine_profiles.py','settings_api.py','station_settings.py','launch.py']


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack_wheel(path,destination):
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith('/'): continue
            relative=Path(name)
            parts=relative.parts
            if '..' in parts or relative.is_absolute(): raise ValueError('Unsafe wheel path')
            if parts[0].endswith('.data'):
                if len(parts)<3 or parts[1] not in ('purelib','platlib'): continue
                relative=Path(*parts[2:])
            target=destination/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(name))


def build(variant, include_samples=True):
    name='XRayReview-Windows-x64-'+variant.upper()
    output=ROOT/'dist'/name
    if output.exists(): shutil.rmtree(output)
    runtime=output/'runtime'; runtime.mkdir(parents=True)
    app=output/'_app'; app.mkdir()
    for folder in ('config','models','workspace/data','logs','licenses','prerequisites'):
        (output/folder).mkdir(parents=True)
    miniz_license=ROOT/'build/miniz/LICENSE'
    if miniz_license.is_file():shutil.copyfile(miniz_license,output/'licenses/MINIZ-LICENSE.txt')
    embedded=CACHE/'python-3.14.10-embed-amd64.zip'
    assert sha(embedded)=='90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
    with zipfile.ZipFile(embedded) as archive:archive.extractall(runtime)
    # The ._pth file controls the isolated interpreter's entire import path.
    (runtime/'python314._pth').write_text('python314.zip\n.\nLib/site-packages\n../_app\nimport site\n',encoding='utf-8')
    wheels=sorted((CACHE/('wheels-'+variant)).glob('*.whl'))
    assert len(wheels)>=15,'Incomplete wheel cache'
    for wheel in wheels: unpack_wheel(wheel,runtime/'Lib/site-packages')
    for path in (CACHE/'vc-runtime').glob('*.dll_amd64'):
        shutil.copyfile(path,runtime/path.name.removesuffix('_amd64'))
    assert (runtime/'msvcp140.dll').exists()
    shutil.copyfile(CACHE/'VC_redist.x64.exe',output/'prerequisites/VC_redist.x64.exe')
    shutil.copyfile(CACHE/'XRayReview.exe',output/'XRayReview.exe')
    for filename in SOURCES:shutil.copyfile(ROOT/filename,app/filename)
    for filename in ('portable_entry.py','portable_selftest.py'):
        shutil.copyfile(ROOT/'packaging'/filename,app/filename)
    shutil.copytree(ROOT/'templates',app/'templates')
    shutil.copytree(ROOT/'static',app/'static')
    for filename in ('IPC_SETUP.md','V2_IPC_DESIGN.md','UI_WORKFLOW.md'):
        shutil.copyfile(ROOT/'docs'/filename,output/filename)
    shutil.copytree(ROOT/'models/noop-v1',output/'models/noop-v1')
    if include_samples:
        for filename in ('ok_0.png','ng_5.png','ng_9.png'):
            shutil.copyfile(ROOT/'data'/filename,output/'workspace/data'/filename)
    # This is an explicit diagnostic fixture, never an enabled screw classifier.
    import sys
    sys.path.insert(0,str(ROOT))
    from verify_settings import fixture
    (app/'selftest.onnx').write_bytes(fixture())
    config=dict(schema_version=1,station_id='WINDOWS-TEST',workspace='../workspace',
                model_root='../models',default_provider='cpu' if variant=='cpu' else 'require_cuda',
                acquisition=dict(enabled=False,source='',poll_seconds=3,stable_seconds=15),
                allow_cpu_fallback=variant=='cpu')
    (output/'config/station.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    fingerprint=hashlib.sha256(b''.join((app/name).read_bytes() for name in SOURCES)).hexdigest()
    (app/'build_fingerprint.txt').write_text(fingerprint,encoding='ascii')
    if variant=='cpu':
        manual=ROOT/'output/pdf/Windows-CPU-操作手冊.pdf'
        if not manual.is_file():
            raise FileNotFoundError('先執行 docs/windows-cpu-manual/build_manual.py 產生操作手冊')
        shutil.copyfile(manual,output/manual.name)
    text=(ROOT/'packaging/WINDOWS_README.txt').read_text(encoding='utf-8').replace('{VARIANT}',variant.upper())
    if not include_samples:
        text='公開交付版：不含原始測試照片。首次請開啟「工程設定 → 機型與參考圖」新增機型及正常參考圖，再到現場頁面選取機型與來源。最新操作請依 UI_WORKFLOW.md；PDF 的舊版畫面僅供判讀參考。\n\n'+text
        text=text.replace('workspace\\data\\ok_0.png：正常參考\nworkspace\\data\\ng_5.png、ng_9.png：既有兩張測試照片','本公開包不含原始測試照片；請使用現場自行提供的正常參考圖與待測照。')
    if variant=='cpu':
        text='最新介面請先閱讀 UI_WORKFLOW.md；Windows-CPU-操作手冊.pdf 為舊版圖文參考及現場勾選表。\n\n'+text
    (output/'READ-ME-FIRST.txt').write_text(text,encoding='utf-8-sig')
    (output/'DIAGNOSTICS.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\nXRayReview.exe --self-test\r\necho.\r\necho Diagnostic report: logs\\windows-selftest.json\r\npause\r\n',encoding='ascii',newline='')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest=dict(variant=variant,include_samples=include_samples,source_commit=commit,python='3.14.10',architecture='AMD64',
                  windows_execution_verified=False,model='noop until the operator applies a trained model',
                  inputs=[dict(file=p.name,sha256=sha(p)) for p in [embedded,CACHE/'VC_redist.x64.exe',CACHE/'XRayReview.exe',*wheels]],
                  file_sha256={str(p.relative_to(output)).replace('\\','/'):sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    (output/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # Preserve each package's full metadata and license files in site-packages.
    (output/'licenses/THIRD-PARTY.txt').write_text('Python license: runtime/LICENSE.txt\nPackage licenses: runtime/Lib/site-packages/*.dist-info/licenses (and LICENSE files)\nMicrosoft runtime: extracted from official VC_redist.x64.exe, original installer retained in prerequisites.\nhttps://www.python.org/downloads/release/python-31410/\nhttps://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist\nhttps://pypi.org/\n',encoding='utf-8')
    manifest['file_sha256']['licenses/THIRD-PARTY.txt']=sha(output/'licenses/THIRD-PARTY.txt')
    (output/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=ROOT/'dist'/(name+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(output.parent))
    (archive.with_suffix('.zip.sha256')).write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(dict(zip=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--variant',choices=['cpu','gpu'],required=True)
    parser.add_argument('--without-samples',action='store_true',help='Public distribution without original X-ray input photos')
    args=parser.parse_args()
    build(args.variant,include_samples=not args.without_samples)
