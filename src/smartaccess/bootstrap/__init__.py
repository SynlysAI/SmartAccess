"""SmartAccess 启动与依赖装配入口。"""

from __future__ import annotations

from smartaccess.bootstrap.runtime import (
    build_edge_app,
    build_experiment_service,
    build_runtime_facade,
    serve_edge_api,
)
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.logging import configure_logging


def run_desktop(settings: AppSettings | None = None) -> int:
    """启动 SmartAccess 桌面工作台。

    Args:
        settings: 可选应用配置；为空时从环境变量和 .env 读取。

    Returns:
        Qt 应用退出码。
    """

    settings = settings or AppSettings.from_env()
    configure_logging(settings)
    facade = build_runtime_facade(settings)

    from smartaccess.desktop.shell.app import run_app

    return run_app(settings, facade)
