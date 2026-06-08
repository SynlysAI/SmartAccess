"""启动 SmartAccess 桌面应用的便捷脚本"""

import os
import sys
from pathlib import Path

# 加载 .env 文件
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

print("=" * 60)
print("启动 SmartAccess 桌面应用")
print("=" * 60)

# 显示当前配置
from smartaccess.shared.config.settings import AppSettings

settings = AppSettings.from_env()
print(f"\n当前配置:")
print(f"  - 工作区目录: {settings.workspace_dir}")
print(f"  - 工作流生成器: {settings.workflow_generator_provider}")
print(f"  - 自动化提供者: {settings.automation_provider}")
print(f"  - DeepSeek 已配置: {'是' if settings.deepseek_configured else '否'}")

print("\n" + "=" * 60)
print("正在启动...")
print("=" * 60 + "\n")

# 启动桌面应用
from smartaccess.bootstrap import run_desktop

sys.exit(run_desktop(settings))
