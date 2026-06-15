"""启动 SmartAccess 桌面应用的便捷脚本"""

import sys

print("=" * 60)
print("启动 SmartAccess 桌面应用")
print("=" * 60)

# 显示当前配置
from smartaccess.shared.config.settings import AppSettings

settings = AppSettings.from_env()
active_profile = settings.ai_active_profile_config
ai_label = (
    f"{active_profile.label} / {active_profile.model}"
    if active_profile is not None
    else "Template / local rules"
)
ai_key_status = "set" if active_profile is not None and active_profile.configured else "missing"
print(f"\n当前配置:")
print(f"  - 工作区目录: {settings.workspace_dir}")
print(f"  - AI profile: {settings.ai_active_profile or 'none'}")
print(f"  - AI model: {ai_label}")
print(f"  - AI key: {ai_key_status}")
print(f"  - 自动化提供者: {settings.automation_provider}")

print("\n" + "=" * 60)
print("正在启动...")
print("=" * 60 + "\n")

# 启动桌面应用
from smartaccess.bootstrap import run_desktop

sys.exit(run_desktop(settings))
