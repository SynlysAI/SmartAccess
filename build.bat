@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "OUTPUT_DIR=%ROOT%\dist"
set "ICON=%ROOT%\resource\icon.ico"

set "MODE=folder"

REM 只改这一处：venv 使用项目 .venv；conda 使用已激活的 smartaccess 环境。
set "ENV_MODE=venv"

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

if /i "%ENV_MODE%"=="conda" (
    call conda activate smartaccess
    if errorlevel 1 (
        echo [ERROR] Failed to activate conda environment 'smartaccess'
        pause
        exit /b 1
    )
    set "PYTHON=python"
    set "SITE_PACKAGES=%CONDA_PREFIX%\Lib\site-packages"
) else (
    set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
    set "SITE_PACKAGES=%ROOT%\.venv\Lib\site-packages"
    if not exist "%ROOT%\.venv\Scripts\python.exe" (
        echo [ERROR] Virtual environment not found: %ROOT%\.venv
        echo [ERROR] Create .venv and install dependencies before building.
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import nuitka" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Nuitka not installed in .venv
    echo [ERROR] Run: "%PYTHON%" -m pip install nuitka ordered-set zstandard
    pause
    exit /b 1
)

echo [INFO] Mode: %MODE%
echo [INFO] Output: %OUTPUT_DIR%
echo.

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

set "BUILD_START_TIME=%TIME: =0%"

set "CMD=--standalone"
set "CMD=%CMD% --assume-yes-for-downloads"
set "CMD=%CMD% --windows-console-mode=disable"
set "CMD=%CMD% --enable-plugin=pyqt6"
set "CMD=%CMD% --include-package=smartaccess"
set "CMD=%CMD% --nofollow-import-to=cv2"
set "CMD=%CMD% --nofollow-import-to=paddle"
set "CMD=%CMD% --nofollow-import-to=paddleocr"
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

set "NUITKA_CMD=%CMD%"
"%PYTHON%" -m nuitka !NUITKA_CMD!
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

if "%MODE%"=="folder" (
    call :copy_runtime_packages
    if errorlevel 1 (
        call :show_duration
        pause
        exit /b 1
    )
)

set "RELEASE_ZIP="
if "%MODE%"=="folder" (
    call :package_release
    if errorlevel 1 (
        call :show_duration
        pause
        exit /b 1
    )
)

echo.
echo ==========================================
echo Build complete!
echo ==========================================
echo.
echo Output: %OUTPUT_DIR%\run_desktop.dist\
if defined RELEASE_ZIP echo Release: %RELEASE_ZIP%
echo.
call :show_duration
echo.
echo Next steps:
echo   1. Copy .envexample to .env
echo   2. Edit .env with your API keys
echo   3. Run run_desktop.exe
if defined RELEASE_ZIP echo   4. Publish %RELEASE_ZIP% to GitHub Release
echo.
pause
exit /b 0

:copy_runtime_packages
echo.
echo [STEP] Copying OpenCV and Paddle runtime packages...
for %%P in (cv2 paddle paddleocr) do (
    if not exist "%SITE_PACKAGES%\%%P" (
        echo [ERROR] Missing runtime package: %SITE_PACKAGES%\%%P
        exit /b 1
    )
    if exist "%OUTPUT_DIR%\run_desktop.dist\%%P" rmdir /s /q "%OUTPUT_DIR%\run_desktop.dist\%%P"
    robocopy "%SITE_PACKAGES%\%%P" "%OUTPUT_DIR%\run_desktop.dist\%%P" /E /NFL /NDL /NJH /NJS /NP
    if errorlevel 8 (
        echo [ERROR] Failed to copy runtime package %%P
        exit /b 1
    )
    echo [INFO] Copied %%P
)
exit /b 0

:package_release
set "VERSION_FILE=%TEMP%\smartaccess-version.txt"
"%PYTHON%" "%ROOT%\scripts\read_version.py" > "%VERSION_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to read application version
    exit /b 1
)
set /p APP_VERSION=<"%VERSION_FILE%"
del /f /q "%VERSION_FILE%"
if not defined APP_VERSION (
    echo [ERROR] Failed to read application version
    exit /b 1
)

set "RELEASE_ZIP=%OUTPUT_DIR%\SmartAccess-v%APP_VERSION%.zip"
echo.
echo [STEP] Packaging %RELEASE_ZIP%...

if exist "%RELEASE_ZIP%" del /f /q "%RELEASE_ZIP%"
"%PYTHON%" "%ROOT%\scripts\package_release.py" "%OUTPUT_DIR%\run_desktop.dist" "%RELEASE_ZIP%"
if errorlevel 1 (
    echo [ERROR] Failed to create release zip
    exit /b 1
)
echo [INFO] Release package: %RELEASE_ZIP%
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
