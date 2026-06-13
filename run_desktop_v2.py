"""启动 SmartAccess 桌面应用 v2 的便捷脚本。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv(env_path: Path) -> None:
    """从项目根目录的 .env 文件加载环境变量。

    Args:
        env_path: .env 文件路径。
    """

    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _clean_env_value(value)


def _clean_env_value(value: str) -> str:
    """清理 .env 中的引号包裹值。"""

    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        return cleaned[1:-1]
    return cleaned


def main() -> int:
    """加载配置并启动 SmartAccess 桌面应用。"""

    project_root = Path(__file__).resolve().parent
    _load_dotenv(project_root / ".env")

    from smartaccess_v2.bootstrap import run_desktop
    from smartaccess_v2.shared.config.settings import AppSettings
    from smartaccess_v2.shared.logging import configure_logging

    settings = AppSettings.from_env()
    logger = configure_logging(settings)
    logger.info("启动 SmartAccess 桌面应用")
    logger.info("工作区目录: %s", settings.workspace_dir)
    logger.info("自动化提供者: %s", settings.automation_provider)
    logger.info("视觉提供者: %s", settings.vision_provider)
    logger.info("AI 提供者: %s", settings.ai_provider)

    return run_desktop(settings)


if __name__ == "__main__":
    sys.exit(main())
