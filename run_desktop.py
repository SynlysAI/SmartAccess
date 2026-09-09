"""启动 SmartAccess 桌面应用的便捷脚本。"""

from __future__ import annotations

import sys


def main() -> int:
    """加载配置并启动 SmartAccess 桌面应用。"""

    from smartaccess.bootstrap import run_desktop
    from smartaccess.shared.config.settings import AppSettings
    from smartaccess.shared.logging import configure_logging

    settings = AppSettings.from_env()
    logger = configure_logging(settings)
    logger.info("启动 SmartAccess 桌面应用")
    logger.info("工作区目录: %s", settings.workspace_dir)
    logger.info(
        "SmartAccess 执行端 ID: %s",
        settings.device_id or "未配置",
    )
    logger.info("自动化提供者: %s", settings.automation_provider)
    logger.info("视觉提供者: %s", settings.vision_provider)
    logger.info("AI 文字模型: %s / %s", settings.ai_text_provider, settings.ai_text_model)
    logger.info("AI 多模态模型: %s / %s", settings.ai_vision_provider, settings.ai_vision_model)

    return run_desktop(settings)


if __name__ == "__main__":
    sys.exit(main())
