@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "OUTPUT_DIR=%ROOT%\dist"
set "ICON=%ROOT%\resource\icon.ico"

set "MODE=folder"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--onefile" (
    set "MODE=onefile"
    shift
    goto :parse_args
)
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
shift
goto :parse_args
:args_done

echo ==========================================
echo     SmartAccess Nuitka Build
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found, please activate smartaccess env
    exit /b 1
)

python -m nuitka --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Nuitka not installed, run: pip install nuitka ordered-set zstandard
    exit /b 1
)

echo [INFO] Mode: %MODE%
echo [INFO] Output: %OUTPUT_DIR%
echo.

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

set "CMD=python -m nuitka"
set "CMD=%CMD% --standalone"
set "CMD=%CMD% --windows-console-mode=disable"
set "CMD=%CMD% --enable-plugin=pyqt6"
set "CMD=%CMD% --include-package=smartaccess"
set "CMD=%CMD% --include-package=cv2"
set "CMD=%CMD% --include-package=paddleocr"
set "CMD=%CMD% --include-package=paddle"
set "CMD=%CMD% --include-package=pydantic"
set "CMD=%CMD% --include-package=fastapi"
set "CMD=%CMD% --include-package=pika"
set "CMD=%CMD% --include-data-dir=%ROOT%\resource=resource"
set "CMD=%CMD% --output-dir=%OUTPUT_DIR%"
set "CMD=%CMD% --remove-output"

if exist "%ICON%" (
    set "CMD=%CMD% --windows-icon-from-ico=%ICON%"
)

if "%MODE%"=="onefile" (
    set "CMD=%CMD% --onefile"
)

set "CMD=%CMD% %ROOT%\run_desktop.py"

echo [STEP] Building with Nuitka...
echo.

%CMD%
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed
    exit /b 1
)

echo.
echo [STEP] Copying config template...

if exist "%ROOT%\.envexample" (
    copy "%ROOT%\.envexample" "%OUTPUT_DIR%\run_desktop.dist\.envexample" > nul
)

echo.
echo ==========================================
echo Build complete!
echo ==========================================
echo.
echo Output: %OUTPUT_DIR%\run_desktop.dist\
echo.
echo Next steps:
echo   1. Copy .envexample to .env
echo   2. Edit .env with your API keys
echo   3. Run run_desktop.exe
echo.
exit /b 0

:show_help
echo Usage:
echo   build.bat              Build as folder (recommended)
echo   build.bat --onefile    Build as single exe
echo   build.bat --help       Show this help
echo.
exit /b 0
