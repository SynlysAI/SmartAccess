@echo off
setlocal enabledelayedexpansion
REM SmartAccess 离线 base 包构建脚本
REM 把 runtime\ + .venv\ 打包成 zip, 供实验室机器离线部署
REM 源码不打包 (走 git clone/pull), workspace/.env/.git 不打包 (含密钥/运行时数据)

REM 用法:
REM   make_base_package.bat              默认打包到 dist\smartaccess-base-YYYYMMDD.zip
REM   make_base_package.bat <name.zip>   指定输出文件名
REM   make_base_package.bat --help       显示帮助

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "RUNTIME_DIR=%ROOT%\runtime"
set "VENV_DIR=%ROOT%\.venv"
set "DIST_DIR=%ROOT%\dist"

REM 解析输出名
set "ZIP_NAME=%~1"
if /i "%ZIP_NAME%"=="--help" goto :show_help
if /i "%ZIP_NAME%"=="-h" goto :show_help
if /i "%ZIP_NAME%"=="/?" goto :show_help
if "%ZIP_NAME%"=="" (
    REM 用日期生成默认名
    for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value 2^>nul ^| find "="') do set "LDT=%%a"
    if defined LDT (
        set "DATE_STAMP=!LDT:~0,8!"
    ) else (
        set "DATE_STAMP=unknown"
    )
    set "ZIP_NAME=smartaccess-base-!DATE_STAMP!.zip"
)

REM 规整路径: 如果用户只给文件名, 放到 dist\
set "ZIP_PATH=%ZIP_NAME%"
echo "%ZIP_NAME%" | findstr /r "\\\\ :" > nul
if errorlevel 1 set "ZIP_PATH=%DIST_DIR%\%ZIP_NAME%"

echo ==========================================
echo     SmartAccess 离线 Base 包构建
echo ==========================================
echo.

REM 前置检查: runtime\python
if not exist "%RUNTIME_DIR%\python.exe" (
    echo [ERROR] runtime\python\python.exe 不存在
    echo        请先成功运行 install.bat 完成初次安装
    exit /b 1
)

REM 前置检查: .venv
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [ERROR] .venv 未创建或缺失 Scripts\python.exe
    echo        请先成功运行 install.bat 完成初次安装
    exit /b 1
)

REM 创建 dist 目录
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

echo [INFO] 输出文件: %ZIP_PATH%
echo [INFO] 包含:
echo          - runtime\        ^(嵌入式 Python^)
echo          - .venv\          ^(已安装的虚拟环境^)
echo [INFO] 排除:
echo          - src\ docs\ tests\ ai\  ^(源码 / 文档^)
echo          - workspace\              ^(运行时数据^)
echo          - .env                    ^(密钥配置^)
echo          - .git\ dist\             ^(版本控制 / 产出^)
echo          - __pycache__ *.pyc       ^(缓存^)
echo.

REM 清理缓存, 能显著减小包体积
echo [STEP 1/3] 清理 __pycache__ 和 .pyc 缓存
powershell -NoProfile -Command ^
    "$count=0; " ^
    "Get-ChildItem -Path '%RUNTIME_DIR%','%VENV_DIR%' -Recurse -Force -Include '__pycache__','*.pyc' -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue; $count++ }; " ^
    "Write-Host ('  清理条目: ' + $count)"
echo.

REM 检查 tar 是否可用 (Windows 10 1803+ 自带)
echo [STEP 2/3] 打包
where tar >nul 2>nul
if errorlevel 1 (
    echo [WARNING] 未找到 tar, 回退到 PowerShell Compress-Archive ^(较慢^)
    goto :pack_powershell
)

:pack_tar
REM tar -a 根据扩展名自动选格式; zip 走 libarchive 的 zip 编码器, 大文件性能远好于 Compress-Archive
if exist "%ZIP_PATH%" (
    echo [INFO] 已存在同名文件, 删除后重建
    del "%ZIP_PATH%"
)
pushd "%ROOT%"
tar -a -c -f "%ZIP_PATH%" runtime .venv
set "TAR_EXIT=%errorlevel%"
popd
if not "%TAR_EXIT%"=="0" (
    echo [ERROR] tar 打包失败 ^(exit=%TAR_EXIT%^)
    echo        可尝试删除目标文件后重试, 或回退到 PowerShell:
    echo        powershell -Command "Compress-Archive -Path 'runtime','.venv' -DestinationPath '%ZIP_PATH%' -CompressionLevel Optimal"
    exit /b 1
)
goto :pack_done

:pack_powershell
powershell -NoProfile -Command ^
    "if (Test-Path '%ZIP_PATH%') { Remove-Item '%ZIP_PATH%' -Force }; " ^
    "Compress-Archive -Path '%RUNTIME_DIR%','%VENV_DIR%' -DestinationPath '%ZIP_PATH%' -CompressionLevel Optimal"
if errorlevel 1 (
    echo [ERROR] PowerShell 打包失败
    exit /b 1
)

:pack_done
echo.

REM 输出包大小
echo [STEP 3/3] 完成
powershell -NoProfile -Command ^
    "if (Test-Path '%ZIP_PATH%') { $f = Get-Item '%ZIP_PATH%'; $mb = [math]::Round($f.Length / 1MB, 1); Write-Host ('  文件大小: ' + $mb + ' MB') } else { Write-Host '  [ERROR] 输出文件不存在' }"

echo.
echo ==========================================
echo 打包成功^!
echo ==========================================
echo.
echo 部署到新机器的步骤:
echo   1. 把 zip 拷到目标机器的部署目录
echo   2. 解压 ^(Windows 资源管理器右键 -^> 全部解压缩^)
echo   3. 在解压目录里 git clone SmartAccess 源码 ^(或 git pull 更新^)
echo      确保 src\, pyproject.toml, start_app.bat, run_desktop.py 都在
echo   4. 复制 .envexample -^> .env 并填入 AI 密钥 / SpecLabOS 配置
echo   5. 双击 start_app.bat 启动
echo.
echo 注意:
echo   - start_app.bat 会自动修复 .venv\pyvenv.cfg 和 .pth 路径
echo   - paddleocr 模型文件不在包内, 首次使用 OCR 会自动下载
echo   - 源码走 git 管理, 后续更新只需 git pull, 无需重打 base 包
echo.
exit /b 0

:show_help
echo 用法:
echo   make_base_package.bat              使用默认文件名: dist\smartaccess-base-YYYYMMDD.zip
echo   make_base_package.bat myname.zip   指定输出文件名 ^(仅文件名时放到 dist\^)
echo   make_base_package.bat D:\foo.zip   指定完整输出路径
echo   make_base_package.bat --help       显示本帮助
echo.
echo 前置条件:
echo   必须先成功运行 install.bat ^(确保 .venv 已装齐所有依赖^)
echo.
echo 产物说明:
echo   仅打包 runtime\ + .venv\, 不含源码/配置/运行时数据
echo   源码靠 git clone/pull, 配置靠用户手动复制 .envexample -^> .env
echo.
exit /b 0
