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

call conda activate smartaccess
if errorlevel 1 (
    echo [ERROR] Failed to activate conda environment 'smartaccess'
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found, please activate smartaccess env
    pause
    exit /b 1
)

python -m nuitka --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Nuitka not installed, run: pip install nuitka ordered-set zstandard
    pause
    exit /b 1
)

echo [INFO] Mode: %MODE%
echo [INFO] Output: %OUTPUT_DIR%
echo.

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

set "BUILD_START_TIME=%TIME: =0%"

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
    call :show_duration
    pause
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
call :show_duration
echo.
echo Next steps:
echo   1. Copy .envexample to .env
echo   2. Edit .env with your API keys
echo   3. Run run_desktop.exe
echo.
pause
exit /b 0

:show_help
echo Usage:
echo   build.bat              Build as folder (recommended)
echo   build.bat --onefile    Build as single exe
echo   build.bat --help       Show this help
echo.
exit /b 0

:show_duration
set "BUILD_END_TIME=%TIME: =0%"
set /a BUILD_START_SECONDS=1%BUILD_START_TIME:~0,2%-100
set /a BUILD_START_SECONDS=BUILD_START_SECONDS*3600+1%BUILD_START_TIME:~3,2%-100*60+1%BUILD_START_TIME:~6,2%-100
set /a BUILD_END_SECONDS=1%BUILD_END_TIME:~0,2%-100
set /a BUILD_END_SECONDS=BUILD_END_SECONDS*3600+1%BUILD_END_TIME:~3,2%-100*60+1%BUILD_END_TIME:~6,2%-100
set /a BUILD_ELAPSED_SECONDS=BUILD_END_SECONDS-BUILD_START_SECONDS
if %BUILD_ELAPSED_SECONDS% LSS 0 set /a BUILD_ELAPSED_SECONDS+=24*3600
set /a BUILD_ELAPSED_HOURS=BUILD_ELAPSED_SECONDS/3600
set /a BUILD_ELAPSED_MINUTES=(BUILD_ELAPSED_SECONDS%%3600)/60
set /a BUILD_ELAPSED_REMAINING_SECONDS=BUILD_ELAPSED_SECONDS%%60
if %BUILD_ELAPSED_HOURS% LSS 10 set "BUILD_ELAPSED_HOURS=0%BUILD_ELAPSED_HOURS%"
if %BUILD_ELAPSED_MINUTES% LSS 10 set "BUILD_ELAPSED_MINUTES=0%BUILD_ELAPSED_MINUTES%"
if %BUILD_ELAPSED_REMAINING_SECONDS% LSS 10 set "BUILD_ELAPSED_REMAINING_SECONDS=0%BUILD_ELAPSED_REMAINING_SECONDS%"
echo [INFO] Start time: %BUILD_START_TIME%
echo [INFO] End time:   %BUILD_END_TIME%
echo [INFO] Elapsed:    %BUILD_ELAPSED_HOURS%:%BUILD_ELAPSED_MINUTES%:%BUILD_ELAPSED_REMAINING_SECONDS%
exit /b 0
