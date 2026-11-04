"""Build fresh CPU app + isolated GPU worker; never overwrite an older release."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
NAME='XRayReview-DINO-Optimized-r3-20261104-Windows-x64'
MODEL='dino-paired-optimized-47-20261104-r3'
OUT=ROOT/'dist'/NAME
BUILD=ROOT/'build/optimized-r3-20261104'
ENGINE=('detector.py','registration_candidate.py','single_reference_evidence.py','wire_review.py','model_manager.py','model_adapters.py','library.py','machine_profiles.py','detection_runtime.py','brightness_fit.py','dino_adapter.py','dino_paired_optimized.py','paired_geometry.py')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def freeze():
    if OUT.exists():raise FileExistsError(OUT)
    BUILD.mkdir(parents=True,exist_ok=True)
    (BUILD/'build_fingerprint.txt').write_text('|'.join(sha(ROOT/p) for p in ENGINE),encoding='ascii')
    env=dict(os.environ,PYTHONPATH=str(ROOT/'build/pyinstaller-tools'),PYTHONIOENCODING='utf-8')
    commands=[('app',ROOT/'.venv/Scripts/python.exe','XRayReview',ROOT/'packaging/frozen_entry.py'),
              ('gpu',ROOT/'workspace/venvs/dino-directml/Scripts/python.exe','XRayGpuWorker',ROOT/'gpu_worker.py')]
    for kind,python,name,entry in commands:
        cmd=[str(python),'-m','PyInstaller','--noconfirm','--onedir','--console','--name',name,
             '--distpath',str(BUILD/'frozen'), '--workpath',str(BUILD/('work-'+kind)),
             '--specpath',str(BUILD/('spec-'+kind)),'--paths',str(ROOT),'--paths',str(ROOT/'packaging'),
             '--collect-binaries','onnxruntime','--exclude-module','onnx']
        if kind=='app':
            for source,target in [(ROOT/'templates','templates'),(ROOT/'static','static'),(BUILD/'build_fingerprint.txt','.')]:
                cmd+=['--add-data',str(source)+';'+target]
        cmd.append(str(entry))
        with (BUILD/('freeze-'+kind+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        print('Frozen '+kind,flush=True)


def assemble():
    if OUT.exists():raise FileExistsError(OUT)
    shutil.copytree(BUILD/'frozen/XRayReview',OUT)
    shutil.copytree(BUILD/'frozen/XRayGpuWorker',OUT/'runtime-gpu')
    for name in (MODEL,'dino-paired-47-20261103','dino-examples-a3b8c97aa539','clip-examples-916f8a7fd458','noop-v1'):
        shutil.copytree(ROOT/'models'/name,OUT/'models'/name)
    write(OUT/'models/active.json',dict(schema_version=1,version_directory=MODEL))
    write(OUT/'config/station.json',dict(schema_version=1,station_id='DINO-OPTIMIZED-R3-20261104',workspace='../workspace',
                                       model_root='../models',default_provider='cpu',allow_cpu_fallback=True,
                                       acquisition=dict(enabled=False,source='',poll_seconds=3,stable_seconds=15)))
    preferences=json.loads((ROOT/'workspace/windows-check/state/ui_settings.json').read_text(encoding='utf-8'))
    profiles=[]
    for profile in preferences['machine_profiles']:
        source=Path(profile['reference'])
        path=Path('workspace/state/machine-references')/source.name
        (OUT/path).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,OUT/path)
        profiles.append(dict(profile,reference=str(path)))
    preferences.update(machine_profiles=profiles,allow_cpu_fallback=True,acquisition=dict(enabled=False,source=''))
    preferences.setdefault('dino_execution','cpu')
    write(OUT/'workspace/state/ui_settings.json',preferences)
    (OUT/'logs').mkdir()
    (OUT/'DIAGNOSTICS.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\nXRayReview.exe --self-test\r\npause\r\n',encoding='ascii')
    (OUT/'開始前請讀我.txt').write_text('''X-RAY DINO 合併優化雙圖 r3｜2026-11-04｜Windows x64

完整解壓縮，再雙擊 XRayReview.exe；不需另裝 Python。
工程頁面 → AI 模型，可以選 CPU 或 NVIDIA GPU。預設 CPU；GPU 工作程式已內附。
GPU 不可用時切回 CPU；不把 CPU 的結果冒充 GPU。
47 張螺絲＋65 張正常範例、參照圖＋待測圖同時啟用。
整體外觀與小區域各占一半，兩張圖各自判斷；待測有螺絲、參照沒有才保留。
僅在兩圖都判成螺絲、且局部幾何條件通過時，各補看一次相同位置小圖。
已整合三項加速與參照資料／影像準備重用。舊 r2 模型仍可切回。
範例管理依然整合於工程頁，可新增並另存新版本。

設定、照片、檢測與人工紀錄儲存在此資料夾的 workspace；搬移需複製整個資料夾。
此為新的可攜資料夾，自動取圖預設關閉；不會自行重跑舊資料。
要更新既有可攜資料夾並保留原 workspace，請使用「更新舊版.cmd」。
完整圖資報告仍為先前實驗報告；本次只重測固定單圖與既有 59 個案例，沒有重跑整批。
舊 r2 報告不能當作 r3 的全圖資準確率結果。仍有已知疑似螺絲漏判，請人工複核。
Windows 執行相容性可用 DIAGNOSTICS.cmd 檢查。
''',encoding='utf-8-sig')
    shutil.copyfile(ROOT/'packaging/update_optimized_portable.ps1',OUT/'update-portable.ps1')
    (OUT/'更新舊版.cmd').write_text('@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-portable.ps1"\r\npause\r\n',encoding='ascii')
    sources=[*ROOT.glob('*.py'),*ROOT.glob('templates/*'),*ROOT.glob('static/*'),ROOT/'packaging/frozen_entry.py',ROOT/'packaging/portable_release_check.py']
    write(OUT/'BUILD-MANIFEST.json',dict(version=NAME,model=MODEL,pipeline='dino-combined-20261104-r3',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),includes_uncommitted_work=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources if p.is_file()},
        engine_sha256={p:sha(ROOT/p) for p in ENGINE},cpu_gpu_selectable=True,reference_pair_rule_enabled=True,
        verification_scope='One full photo and 59 fixed cropped pairs; no full dataset rerun',windows_execution_verified=False))
    # Preserve license metadata from both exact runtime environments.
    for kind,site in [('cpu',ROOT/'.venv/Lib/site-packages'),('gpu',ROOT/'workspace/venvs/dino-directml/Lib/site-packages')]:
        for info in site.glob('*.dist-info'):
            shutil.copytree(info,OUT/'licenses'/kind/info.name)
    pythonbase=Path(subprocess.check_output([sys.executable,'-c','import sys;print(sys.base_prefix)'],text=True).strip())
    shutil.copyfile(pythonbase/'LICENSE.txt',OUT/'licenses/PYTHON-LICENSE.txt')
    print('Assembled '+str(OUT),flush=True)


if __name__=='__main__':
    if '--assemble' in sys.argv:assemble()
    else:freeze();assemble()
