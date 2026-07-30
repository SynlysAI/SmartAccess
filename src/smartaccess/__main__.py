"""支持 `python -m smartaccess` 启动桌面应用。"""

from __future__ import annotations

from smartaccess.bootstrap import run_desktop
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.logging import configure_logging


def main() -> int:
    """加载配置并启动桌面应用。"""

    settings = AppSettings.from_env()
    logger = configure_logging(settings)
    logger.info("通过 python -m smartaccess 启动")
    logger.info("SmartAccess 执行端 ID: %s", settings.device_id or "未配置")
    return run_desktop(settings)


if __name__ == "__main__":
    raise SystemExit(main())
