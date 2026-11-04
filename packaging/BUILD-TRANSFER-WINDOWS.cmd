@echo off
setlocal
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" goto build
where py >nul 2>nul
if errorlevel 1 goto missing
py -3 -m venv .venv
if errorlevel 1 goto failed
:build
.venv\Scripts\python.exe -m pip install -r packaging\requirements-transfer-build.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe packaging\build_transfer.py
if errorlevel 1 goto failed
echo Ready: dist\XRayTransfer\XRayTransfer.exe
start "" "dist\XRayTransfer\XRayTransfer.exe"
pause
exit /b 0
:missing
echo Python 3.11 or newer with Tcl/Tk is required for the one-time build.
echo Or run the build commands with your existing project Python environment.
pause
exit /b 2
:failed
echo Build failed. Keep this window and inspect the error above.
pause
exit /b 2
