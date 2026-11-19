"""GitHub Release 检查与安装目录更新。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from smartaccess import __version__

GITHUB_REPO = "SynlysAI/SmartAccess"
RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_ASSET_PREFIX = "SmartAccess-v"
_ASSET_SUFFIX = ".zip"


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    """GitHub Release 中的发布压缩包。"""

    version: str
    name: str
    download_url: str
    size: int
    sha256: str | None = None


class UpdateError(RuntimeError):
    """检查或安装更新失败。"""


def current_version() -> str:
    """返回当前程序版本号。"""

    return __version__


def is_newer_version(candidate: str, current: str | None = None) -> bool:
    """判断候选版本是否高于当前版本。

    Args:
        candidate: 待比较的发布版本，可带 v 前缀。
        current: 当前版本；为空时读取程序版本。

    Returns:
        候选版本更高时返回 True。
    """

    return _version_key(candidate) > _version_key(current or current_version())


def fetch_latest_release(timeout: float = 20.0) -> ReleaseAsset:
    """读取 GitHub 最新正式发布中的 SmartAccess 压缩包。

    Args:
        timeout: 请求超时秒数。

    Returns:
        最新发布压缩包信息。

    Raises:
        UpdateError: 没有正式发布、没有匹配附件或网络请求失败。
    """

    try:
        payload = _get_json(RELEASE_API_URL, timeout=timeout)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("还没有已发布的正式版本。") from exc
        raise UpdateError(f"检查更新失败：HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"检查更新失败：{exc}") from exc

    tag = str(payload.get("tag_name") or "").strip()
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("发布信息缺少附件。")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        version = _version_from_asset_name(name)
        if version is None:
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if not url:
            continue
        return ReleaseAsset(
            version=version,
            name=name,
            download_url=url,
            size=int(asset.get("size") or 0),
            sha256=_asset_sha256(asset),
        )
    raise UpdateError(
        f"最新发布 {tag or '未知版本'} 中没有 {_ASSET_PREFIX}版本号{_ASSET_SUFFIX} 附件。"
    )


def download_release(asset: ReleaseAsset, timeout: float = 120.0) -> Path:
    """下载发布压缩包并校验摘要。

    Args:
        asset: 发布压缩包信息。
        timeout: 下载超时秒数。

    Returns:
        已校验的临时 zip 路径。

    Raises:
        UpdateError: 下载失败或校验不一致。
    """

    target = Path(tempfile.gettempdir()) / "SmartAccessUpdates" / asset.name
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = Request(
        asset.download_url,
        headers={"User-Agent": "SmartAccess", "Accept": "application/octet-stream"},
    )
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=timeout) as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"下载更新失败：{exc}") from exc

    actual = digest.hexdigest()
    if asset.sha256 and actual.lower() != asset.sha256.lower():
        partial.unlink(missing_ok=True)
        raise UpdateError("下载文件校验失败，已取消更新。")
    partial.replace(target)
    return target


def can_apply_update() -> bool:
    """返回当前程序是否运行在可覆盖的打包目录中。

    Nuitka 独立打包不会设置 sys.frozen，并且 sys.executable 指向
    安装目录中的 python.exe，而不是 run_desktop.exe。
    """

    install_dir = Path(sys.executable).resolve().parent
    if install_dir.name != "SmartAccess":
        return False
    return (install_dir / "run_desktop.exe").is_file()


def launch_update(zip_path: Path) -> None:
    """启动独立更新脚本并让当前程序退出。

    Args:
        zip_path: 已下载的发布压缩包。

    Raises:
        UpdateError: 当前不是打包运行或无法启动更新脚本。
    """

    if not can_apply_update():
        raise UpdateError("当前是开发环境运行，不能覆盖安装目录。请使用打包后的 SmartAccess。")
    install_dir = Path(sys.executable).resolve().parent
    script = _write_update_script(install_dir, zip_path)
    try:
        subprocess.Popen(  # noqa: S603 - 更新脚本路径由本程序生成
            ["cmd", "/c", "start", "", str(script)],
            cwd=str(install_dir.parent),
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"启动更新程序失败：{exc}") from exc


def apply_release_zip(zip_path: Path, install_dir: Path) -> None:
    """把发布压缩包覆盖到现有安装目录。

    只覆盖发布包中的程序文件，保留安装目录里已有的 .env 和 workspace。

    Args:
        zip_path: 发布压缩包路径。
        install_dir: 当前 SmartAccess 安装目录。

    Raises:
        UpdateError: 压缩包结构不符合发布约定。
    """

    staging = install_dir.parent / f".{install_dir.name}.new"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
        if not names or any(not name.startswith("SmartAccess/") for name in names):
            raise UpdateError("更新包结构不正确，解压后必须是 SmartAccess 目录。")
        for info in archive.infolist():
            relative = Path(info.filename.removeprefix("SmartAccess/"))
            if not relative.parts or _is_preserved_path(relative):
                continue
            destination = staging / relative
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    install_dir.mkdir(parents=True, exist_ok=True)
    for path in staging.rglob("*"):
        relative = path.relative_to(staging)
        destination = install_dir / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    shutil.rmtree(staging)


def _is_preserved_path(relative: Path) -> bool:
    """判断安装目录中的用户文件是否应在更新时保留。"""

    return bool(relative.parts) and relative.parts[0] in {".env", "workspace"}


def _write_update_script(install_dir: Path, zip_path: Path) -> Path:
    """生成等待主程序退出后覆盖安装目录的脚本。

    Args:
        install_dir: 当前安装目录。
        zip_path: 发布压缩包路径。

    Returns:
        更新脚本路径。
    """

    pid = os.getpid()
    executable = install_dir / "run_desktop.exe"
    script = Path(tempfile.gettempdir()) / "SmartAccessUpdates" / "apply-update.bat"
    script.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "@echo off",
        "setlocal",
        f"set \"PID={pid}\"",
        f"set \"INSTALL_DIR={install_dir}\"",
        f"set \"ZIP={zip_path}\"",
        f"set \"EXE={executable}\"",
        "set \"EXTRACT=%TEMP%\\SmartAccess-update-extract\"",
        ":wait_exit",
        "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul",
        "if not errorlevel 1 (",
        "    timeout /t 1 /nobreak >nul",
        "    goto :wait_exit",
        ")",
        "if exist \"%EXTRACT%\" rmdir /s /q \"%EXTRACT%\"",
        "mkdir \"%EXTRACT%\"",
        "tar -xf \"%ZIP%\" -C \"%EXTRACT%\"",
        "if errorlevel 1 goto :failed",
        "if not exist \"%EXTRACT%\\SmartAccess\\run_desktop.exe\" goto :failed",
        "robocopy \"%EXTRACT%\\SmartAccess\" \"%INSTALL_DIR%\" /E /XF .env /XD workspace /NFL /NDL /NJH /NJS /NP",
        "if %ERRORLEVEL% GEQ 8 goto :failed",
        "rmdir /s /q \"%EXTRACT%\"",
        "start \"\" \"%EXE%\"",
        "exit /b 0",
        ":failed",
        "echo SmartAccess update failed. > \"%TEMP%\\SmartAccess-update-error.txt\"",
        "exit /b 1",
        "",
    ]
    content = "\r\n".join(lines)
    script.write_text(content, encoding="utf-8")
    return script


def _get_json(url: str, *, timeout: float) -> dict:
    """读取 JSON 接口响应。"""

    request = Request(
        url,
        headers={
            "User-Agent": "SmartAccess",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise UpdateError("更新服务返回了无法识别的数据。")
    return payload


def _version_from_asset_name(name: str) -> str | None:
    """从发布附件名提取版本号。"""

    if not name.startswith(_ASSET_PREFIX) or not name.endswith(_ASSET_SUFFIX):
        return None
    version = name[len(_ASSET_PREFIX) : -len(_ASSET_SUFFIX)].strip()
    parts = version.split(".")
    if len(parts) < 2 or any(not part.isdigit() for part in parts):
        return None
    return version


def _asset_sha256(asset: dict) -> str | None:
    """读取 GitHub 附件的 sha256 摘要。"""

    digest = str(asset.get("digest") or "")
    prefix = "sha256:"
    if digest.lower().startswith(prefix):
        return digest[len(prefix) :]
    return None


def _version_key(version: str) -> tuple[int, ...]:
    """把点分版本号转换为可比较的数字元组。"""

    text = version.strip().lstrip("vV")
    parts = []
    for item in text.split("."):
        number = ""
        for char in item:
            if not char.isdigit():
                break
            number += char
        parts.append(int(number or "0"))
    return tuple(parts)
