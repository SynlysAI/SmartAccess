"""SmartAccess 启动与依赖装配入口。"""

from __future__ import annotations

from smartaccess.bootstrap.heartbeat import (
    HeartbeatReporter,
    start_heartbeat_reporter,
)
from smartaccess.bootstrap.runtime import (
    build_edge_app,
    build_experiment_service,
    build_runtime_facade,
    serve_edge_api,
    start_remote_task_listener,
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

    from smartaccess.desktop.shell.app import show_login_dialog

    if not show_login_dialog(settings):
        return 0

    facade = build_runtime_facade(settings)

    start_remote_task_listener(settings, facade=facade)
    start_heartbeat_reporter(settings, facade=facade)

    from smartaccess.desktop.shell.app import run_app

    return run_app(settings, facade)
