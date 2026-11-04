"""Build a self-contained transfer desktop tool on its target platform."""
import json
from pathlib import Path
import subprocess
import sys

try:
 import tkinter
except ImportError:
 raise SystemExit("缺少 tkinter。Mac 請安裝與 Python 版本相符的 python-tk；Windows 請使用含 Tcl/Tk 的官方 Python。")

try:
 import cryptography
except ImportError:
 raise SystemExit('請先安裝 packaging/requirements-transfer-build.txt 中的加密依賴。')

ROOT=Path(__file__).resolve().parents[1]
stage=ROOT/'build/transfer';stage.mkdir(parents=True,exist_ok=True)
defaults=stage/'transfer-defaults.json'
defaults.write_text(json.dumps(dict(root=str(ROOT),program=str(Path.home()/'Applications/XRayReview-Mac.app/Contents/MacOS/XRayReview-Mac') if sys.platform=='darwin' else str(ROOT/'launch.py'))),encoding='utf-8')
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','XRayTransfer',
 '--paths',str(ROOT/'tools'),'--distpath',str(ROOT/'dist'),'--workpath',str(stage/'work'),'--specpath',str(stage),
 '--add-data',str(defaults)+':.',str(ROOT/'tools/station_transfer_ui.py')]
subprocess.run(command,cwd=ROOT,check=True)
if sys.platform=='darwin':
 bundle=Path.home()/'Applications/XRayTransfer.app';bundle.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['ditto','--noextattr','--norsrc',str(ROOT/'dist/XRayTransfer.app'),str(bundle)],check=True)
 subprocess.run(['xattr','-cr',str(bundle)],check=True)
 subprocess.run(['codesign','--force','--deep','--sign','-',str(bundle)],check=True)
 subprocess.run(['codesign','--verify','--deep','--strict',str(bundle)],check=True)
 print(bundle)
