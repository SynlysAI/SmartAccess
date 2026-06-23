@echo off
setlocal enabledelayedexpansion

REM SmartAccess 环境一键安装脚本
REM 用法:
REM   install.bat                完整安装: 创建 .venv + 装依赖 + 准备 .env
REM   install.bat --update-deps  仅更新依赖, 不重建 .venv
REM   install.bat --portable     强制使用 runtime\python 创建 venv (用于制作离线包的部署机)
REM   install.bat --help         显示帮助

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "EMBED_PY=%ROOT%\runtime\python\python.exe"
set "VENV=%ROOT%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "ENV_EXAMPLE=%ROOT%\.envexample"
set "ENV_FILE=%ROOT%\.env"
set "PYPROJECT=%ROOT%\pyproject.toml"

echo ==========================================
echo     SmartAccess 环境一键安装
echo ==========================================
echo.

REM 解析参数
set "MODE=full"
set "FORCE_PORTABLE=0"
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--update-deps" (
    set "MODE=update-deps"
    shift
    goto :parse_args
)
if /i "%~1"=="--portable" (
    set "FORCE_PORTABLE=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="/?" goto :show_help
echo [ERROR] 未知参数: %~1
exit /b 1
:args_done

REM 前置检查: pyproject.toml
if not exist "%PYPROJECT%" (
    echo [ERROR] 未找到 pyproject.toml
    echo 请确保本脚本位于 SmartAccess 项目根目录
    exit /b 1
)

REM 选择基础 Python: 默认优先系统 Python, --portable 强制用 runtime\python
set "BASE_PY="
if "%FORCE_PORTABLE%"=="1" (
    if not exist "%EMBED_PY%" (
        echo [ERROR] --portable 模式要求 runtime\python\python.exe 存在
        echo        请先准备 runtime\python\ ^(嵌入式 Python 3.12^)
        exit /b 1
    )
    set "BASE_PY=%EMBED_PY%"
    echo [INFO] --portable 模式: 使用嵌入式 Python
    "%EMBED_PY%" --version
    echo.
) else (
    REM 优先尝试系统 Python
    where python >nul 2>nul
    if errorlevel 1 (
        REM 系统没有 python, 尝试 runtime\python
        if exist "%EMBED_PY%" (
            set "BASE_PY=%EMBED_PY%"
            echo [INFO] 系统未检测到 python, 使用 runtime\python\python.exe
            "%EMBED_PY%" --version
            echo.
        ) else (
            echo [ERROR] 系统未检测到 python, 且 runtime\python\python.exe 不存在
            echo.
            echo 解决方案 ^(二选一^):
            echo   1. 安装 Python 3.11+ 到系统 ^(推荐 python.org 官方安装包^)
            echo   2. 从已部署机器拷贝 runtime\python\ ^(用于离线部署^)
            exit /b 1
        )
    ) else (
        REM 系统有 python, 验证版本 ^>= 3.11
        for /f "delims=" %%v in ('python --version 2^>^&1') do set "SYS_PY_VER=%%v"
        echo [INFO] 检测到系统 Python: !SYS_PY_VER!
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
        if errorlevel 1 (
            echo [WARNING] 系统 Python 版本 ^< 3.11, 不满足要求
            if exist "%EMBED_PY%" (
                echo [INFO] 回退到 runtime\python\python.exe
                set "BASE_PY=%EMBED_PY%"
                "%EMBED_PY%" --version
                echo.
            ) else (
                echo [ERROR] 系统 Python 版本不足, 且 runtime\python 不存在
                exit /b 1
            )
        ) else (
            set "BASE_PY=python"
            echo [INFO] 使用系统 Python 创建虚拟环境
            echo        如需制作可移植的离线包, 请加 --portable 参数使用嵌入式 Python
            echo.
        )
    )
)

REM update-deps 模式下, 要求 .venv 已存在
if "%MODE%"=="update-deps" (
    if not exist "%VENV_PY%" (
        echo [ERROR] --update-deps 模式要求 .venv 已存在
        echo 当前未检测到 %VENV_PY%
        echo 请先运行 install.bat ^(不带参数^) 完成初次安装
        exit /b 1
    )
)

if "%MODE%"=="full" goto :step_create_venv
if "%MODE%"=="update-deps" goto :step_install_deps

:step_create_venv
echo [STEP 1/3] 创建虚拟环境 .venv
if exist "%VENV%\Scripts\python.exe" (
    echo [INFO] .venv 已存在, 跳过创建
    echo        如需重建请先退出脚本, 删除 .venv 目录后重跑
) else (
    "%BASE_PY%" -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] 创建 .venv 失败
        exit /b 1
    )
)
echo.

:step_install_deps
echo [STEP 2/3] 安装依赖
echo [INFO] 升级 pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] pip 升级失败
    exit /b 1
)

echo.
echo [INFO] 安装项目主依赖 ^(pydantic, fastapi, PyQt6, uvicorn, pika...^)
"%VENV_PIP%" install -e ".[desktop,serve,dev]"
if errorlevel 1 (
    echo [ERROR] 主依赖安装失败
    echo        请检查网络或 pip 镜像配置
    exit /b 1
)

echo.
echo [INFO] 安装 OCR 依赖 ^(opencv-contrib-python, paddlepaddle, paddleocr^)
echo [INFO] 包体较大, 首次安装可能需要数分钟, 请耐心等待...
"%VENV_PIP%" install opencv-contrib-python paddlepaddle paddleocr
if errorlevel 1 (
    echo.
    echo [WARNING] ============================================
    echo [WARNING] OCR 依赖安装失败
    echo [WARNING] 不使用 OCR 功能可忽略此警告
    echo [WARNING] 需要时请手动重试或配国内镜像:
    echo [WARNING]   pip install opencv-contrib-python paddlepaddle paddleocr -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo [WARNING] ============================================
) else (
    echo [INFO] OCR 依赖安装完成
)
echo.

if "%MODE%"=="update-deps" goto :finish

:step_prepare_env
echo [STEP 3/3] 准备 .env 配置文件
if exist "%ENV_FILE%" (
    echo [INFO] .env 已存在, 跳过 ^(如需重置请先手动删除^)
) else if exist "%ENV_EXAMPLE%" (
    copy "%ENV_EXAMPLE%" "%ENV_FILE%" > nul
    echo [INFO] 已复制 .envexample -^> .env
    echo        请按需编辑 .env 填入 AI 密钥 / SpecLabOS 地址等配置
) else (
    echo [WARNING] 未找到 .envexample, 跳过 .env 创建
)
echo.

:finish
echo [INFO] 依赖清单:
"%VENV_PY%" -c "import sys; print(f'  Python: {sys.version}')"
"%VENV_PY%" -c "import smartaccess; print(f'  smartaccess: editable install OK')" 2>nul || echo [WARNING] smartaccess 未正确安装
"%VENV_PY%" -c "import PyQt6; print(f'  PyQt6: OK')" 2>nul || echo [WARNING] PyQt6 未安装
"%VENV_PY%" -c "import cv2; print(f'  opencv: {cv2.__version__}')" 2>nul || echo [WARNING] opencv 未安装
"%VENV_PY%" -c "import paddleocr; print(f'  paddleocr: OK')" 2>nul || echo [WARNING] paddleocr 未安装

echo.
echo ==========================================
echo 环境准备完成^!
echo 现在可以运行:
echo   start_app.bat
echo ==========================================
exit /b 0

:show_help
echo 用法:
echo   install.bat                完整安装: 创建 .venv + 装依赖 + 准备 .env
echo   install.bat --update-deps  仅更新依赖, 不重建 .venv ^(适合 pyproject.toml 变更后^)
echo   install.bat --portable     强制使用 runtime\python 创建 venv ^(制作离线包前的部署机^)
echo   install.bat --help         显示本帮助
echo.
echo Python 选择策略:
echo   默认: 优先使用系统 Python ^(where python^), 版本需 ^>= 3.11
echo         系统无 Python 或版本不足时, 回退到 runtime\python\python.exe
echo   --portable: 强制使用 runtime\python, 不依赖系统 Python
echo         制作离线包分发的部署机建议用此模式, 保证可移植性
echo.
echo 前置条件:
echo   - 系统已装 Python 3.11+ ^(默认模式^)
echo   - 或 runtime\python\python.exe 存在 ^(--portable 模式或回退^)
echo   - 网络连接用于 pip 安装
echo.
echo 国内镜像加速 ^(可选, 在运行前设置环境变量^):
echo   set PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
echo.
exit /b 0
