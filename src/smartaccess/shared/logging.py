"""日志配置工具。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from smartaccess.shared.config.settings import AppSettings

LOGGER_NAME = "smartaccess"


def configure_logging(settings: AppSettings) -> logging.Logger:
    """配置控制台和文件日志。

    Args:
        settings: 应用配置。

    Returns:
        SmartAccess 日志器。
    """

    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_smartaccess_configured", False):
        return logger

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_dir = Path(settings.workspace_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "smartaccess.log", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    setattr(logger, "_smartaccess_configured", True)
    return logger


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """获取 SmartAccess 日志器。

    Args:
        name: 日志器名称。

    Returns:
        日志器实例。
    """

    return logging.getLogger(name)
