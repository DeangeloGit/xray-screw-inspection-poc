@echo off
cd /d "%~dp0"
set "XRAY_WORKSPACE=%~dp0workspace\windows-check"
echo DINO example manager: http://127.0.0.1:18767/engineer/dino-examples
"%~dp0.venv\Scripts\python.exe" -m dino_examples
pause
