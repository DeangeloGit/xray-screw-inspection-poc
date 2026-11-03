$ErrorActionPreference = 'Stop'
$xrayRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $xrayRoot
$xrayPython = Join-Path $xrayRoot '.venv/Scripts/python.exe'
$xrayTarget = Join-Path $xrayRoot 'dist/XRayReview-DINO-Paired-20261103-r2-Windows-x64'
if (Test-Path -LiteralPath $xrayTarget) { throw '交付資料夾已存在，請保留既有版本，另定新版本名稱。' }
& $xrayPython -m pip install --target build/pyinstaller-tools pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw '無法準備建置工具' }
$env:PYTHONPATH = Join-Path $xrayRoot 'build/pyinstaller-tools'
& $xrayPython -m PyInstaller --noconfirm --onedir --console --name XRayReview --distpath build/frozen-dino-20261103-r2 --workpath build/pyinstaller-dino-20261103-r2 --specpath build/r2 --paths $xrayRoot --paths (Join-Path $xrayRoot 'packaging') --add-data "$xrayRoot/templates;templates" --add-data "$xrayRoot/static;static" --collect-binaries onnxruntime --exclude-module onnx packaging/frozen_entry.py
if ($LASTEXITCODE -ne 0) { throw 'EXE 建置失敗' }
& $xrayPython packaging/assemble_dino_portable.py
if ($LASTEXITCODE -ne 0) { throw '封裝失敗' }
& (Join-Path $xrayTarget 'XRayReview.exe') --self-test
if ($LASTEXITCODE -ne 0) { throw 'Windows 實機驗證失敗' }
& $xrayPython packaging/assemble_dino_portable.py --archive
if ($LASTEXITCODE -ne 0) { throw 'ZIP 封裝失敗' }
