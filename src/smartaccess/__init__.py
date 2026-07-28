"""SmartAccess 重构版应用包。"""

from __future__ import annotations

__all__ = [
    "APP_NAME",
    "RELEASE_CHANNEL",
    "RELEASE_DATE",
    "VERSION_DISPLAY",
    "__version__",
]

APP_NAME = "SmartAccess"
__version__ = "0.1.0"
RELEASE_CHANNEL = "内测版"
RELEASE_DATE = "2026年7月24日"


def _format_version(version: str) -> str:
    """将内部 PEP 440 版本号转换为界面展示版本号。

    Args:
        version: 内部版本号。

    Returns:
        带 v 前缀的界面展示版本号。
    """

    if "b" in version:
        stable_version, beta_number = version.split("b", maxsplit=1)
        return f"v{stable_version}-beta.{beta_number}"
    return f"v{version}"


VERSION_DISPLAY = _format_version(__version__)
