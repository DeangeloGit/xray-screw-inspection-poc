@echo off
cd /d "%~dp0"
set "XRAY_WORKSPACE=%~dp0workspace\windows-check"
"%~dp0.venv\Scripts\python.exe" -c "import launch; original=launch.bind_server; launch.bind_server=lambda app: original(app,ports=(18766,0)); launch.main()"
pause
