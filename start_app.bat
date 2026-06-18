@echo off
chcp 65001 > nul

echo ==========================================
echo     SmartAccess Desktop Launcher
echo ==========================================

cd /d "%~dp0"

set "VENV_CFG=.venv\pyvenv.cfg"
set "NEW_HOME=%CD%\runtime\python"
set "PTH_FILE=.venv\Lib\site-packages\_editable_impl_smartaccess.pth"
set "NEW_SRC=%CD%\src"
if exist "%VENV_CFG%" (
    powershell -NoProfile -Command "(Get-Content '%VENV_CFG%') -replace 'home = .*', 'home = %NEW_HOME:\=\\%' | Set-Content '%VENV_CFG%'"
)
if exist "%PTH_FILE%" (
    powershell -NoProfile -Command "(Get-Content '%PTH_FILE%') -replace '^.+$', '%NEW_SRC:\=\\%' | Set-Content '%PTH_FILE%'"
)

echo Starting application...
.venv\Scripts\python.exe run_desktop.py
