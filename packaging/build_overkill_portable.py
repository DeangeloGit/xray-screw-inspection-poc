"""Build and seal an isolated Windows r3 overkill experiment."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from build_optimized_portable import ENGINE, MODEL, ROOT

NAME = 'XRayReview-DINO-r3-Overkill-Pilot-20261105-Windows-x64'
OUT = ROOT / 'dist' / NAME
BUILD = ROOT / 'build' / 'overkill-pilot-20261105'
BASE = ROOT / 'dist' / 'XRayReview-DINO-Optimized-r3-20261104-Windows-x64'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')


def build():
    if OUT.exists():
        raise FileExistsError(OUT)
    BUILD.mkdir(parents=True,exist_ok=True)
    engine=(*ENGINE,'overkill_pilot.py','overkill_release_validation.py')
    (BUILD/'build_fingerprint.txt').write_text('|'.join(digest(ROOT/p) for p in engine),encoding='ascii')
    cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-m','PyInstaller','--noconfirm','--onedir','--console','--name','XRayReview',
         '--distpath',str(BUILD/'frozen'),'--workpath',str(BUILD/'work'),'--specpath',str(BUILD/'spec'),
         '--paths',str(ROOT),'--paths',str(ROOT/'packaging'),'--collect-binaries','onnxruntime','--exclude-module','onnx']
    for p,target in [(ROOT/'templates','templates'),(ROOT/'static','static'),(BUILD/'build_fingerprint.txt','.')]:
        cmd.extend(('--add-data',str(p)+';'+target))
    cmd.append(str(ROOT/'packaging/frozen_entry.py'))
    with (BUILD/'freeze.log').open('w',encoding='utf8') as log:
        subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT/'build/pyinstaller-tools'),PYTHONIOENCODING='utf-8'),
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(BUILD/'frozen'/'XRayReview',OUT)
    for group in ('runtime-gpu','licenses'):
        shutil.copytree(BASE/group,OUT/group)
    for name in (MODEL,'dino-examples-a3b8c97aa539','noop-v1'):
        shutil.copytree(ROOT/'models'/name,OUT/'models'/name)
    save(OUT/'models'/'active.json',dict(schema_version=1,version_directory=MODEL))
    (OUT/'config').mkdir()
    station=json.loads((BASE/'config/station.json').read_text(encoding='utf8'))
    station['station_id']='DINO-R3-OVERKILL-PILOT-20261105'
    save(OUT/'config/station.json',station)
    (OUT/'config/overkill-pilot.enabled').write_text('dino-r3-overkill-pilot-20261105\n',encoding='ascii')
    settings=json.loads((BASE/'workspace/state/ui_settings.json').read_text(encoding='utf8'))
    for profile in settings['machine_profiles']:
        profile['reference']='workspace/state/machine-references/'+Path(profile['reference']).name
    settings.update(dino_execution='cpu',acquisition=dict(enabled=False,source=''))
    shutil.copytree(BASE/'workspace/state/machine-references',OUT/'workspace/state/machine-references')
    save(OUT/'workspace/state/ui_settings.json',settings)
    shutil.copyfile(BASE/'DIAGNOSTICS.cmd',OUT/'DIAGNOSTICS.cmd')
    (OUT/'開始前請讀我.txt').write_text('''X-RAY r3 過殺改善試驗版｜Windows x64｜2026-11-05

完整解壓縮後，雙擊 XRayReview.exe。可直接使用，無須安裝 Python。
DINO 預設使用 47 張螺絲、65 張正常範例與雙圖。工程頁可切換 CPU／GPU，預設 CPU。
此包內建本輪的差分補送、DINO 重看與線材、板件、孔位三項檢查。
試驗規則限定內附的 47＋65 範例庫。範例庫有變動時會沿用 r3 原判斷。
同批案例中，原先辨認的 40 框過殺擋下 39 框。MPT10 六處與 MPT11 10.png 保住。
請用新的資料夾執行。自動取圖預設關閉。資料和複判寫入此包的 workspace。
此包用於離線驗證。同批調整後的結果仍待不同圖資驗證。
''',encoding='utf-8-sig')
    source=[*ROOT.glob('*.py'),*ROOT.glob('templates/*'),*ROOT.glob('static/*'),ROOT/'packaging/frozen_entry.py']
    save(OUT/'BUILD-MANIFEST.json',dict(version=NAME,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        model=MODEL,model_examples=dict(screw=47,normal=65),reference_pair_rule_enabled=True,default_execution='cpu',
        experimental_policy='dino-r3-overkill-pilot-20261105',source_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in source if p.is_file()},
        reused_gpu_worker_sha256=digest(OUT/'runtime-gpu/XRayGpuWorker.exe')))
    print('BUILT',OUT,flush=True)


def seal(checks):
    manifest_path=OUT/'BUILD-MANIFEST.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    assert all(digest(ROOT/p)==h for p,h in manifest['source_sha256'].items())
    receipt=[json.loads(Path(p).read_text(encoding='utf8')) for p in checks]
    assert receipt and all(r['success'] for r in receipt)
    policy=manifest['experimental_policy']
    verified={(r['model']['execution'],len(r['results'])) for r in receipt if r.get('experimental_policy')==policy}
    assert verified=={('gpu',7),('cpu',7),('gpu',4)}
    assert any(r.get('checks') and r['model']['execution']=='cpu' for r in receipt)
    (OUT/'release-checks').mkdir(exist_ok=True)
    for i,r in enumerate(receipt):
        save(OUT/'release-checks'/f'verification-{i+1}.json',r)
    save(manifest_path,dict(manifest,windows_execution_verified=True))
    archive=OUT.with_suffix('.zip')
    if archive.exists():
        raise FileExistsError(archive)
    with ZipFile(archive,'w',ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for p in OUT.rglob('*'):
            if p.is_file():
                z.write(p,p.relative_to(OUT.parent))
    with ZipFile(archive) as z:
        assert z.testzip() is None
    checksum=digest(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n',encoding='ascii')
    print('SEALED',archive,archive.stat().st_size,checksum,flush=True)


if __name__=='__main__':
    if sys.argv[1:2]==['--seal']:
        seal(sys.argv[2:])
    else:
        build()
