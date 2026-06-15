"""确定性的 UI 自动化 Stub。"""

from __future__ import annotations

import time
from typing import Any

from smartaccess.runtime.application.ports import ActionOutcome, WindowInfo
from smartaccess.shared.contracts.anchors import AnchorsContract


class StubAutomationProvider:
    """用于本地运行和服务验证的自动化提供者。"""

    def __init__(self, *, window_title: str = "ElectroChem Console") -> None:
        """初始化 Stub 自动化提供者。

        Args:
            window_title: 模拟窗口标题。
        """

        self._window_title = window_title
        self._profile: AnchorsContract | None = None
        self.actions: list[tuple[str, str | None, Any]] = []

    def configure_profile(self, profile: AnchorsContract | None) -> None:
        """配置当前锚点配置。

        Args:
            profile: 当前锚点配置。
        """

        self._profile = profile

    def window_present(self, title_contains: str | None) -> bool:
        """判断模拟窗口是否匹配。

        Args:
            title_contains: 标题包含文本。

        Returns:
            是否匹配。
        """

        if not title_contains:
            return True
        return title_contains.lower() in self._window_title.lower()

    def discover_windows(self) -> list[WindowInfo]:
        """返回模拟窗口列表。"""

        return [
            WindowInfo(
                title=self._window_title,
                width=1280,
                height=860,
                matched=True,
            )
        ]

    @staticmethod
    def capture_window(hwnd: int) -> bytes | None:
        """返回模拟窗口截图。

        Args:
            hwnd: 窗口句柄。

        Returns:
            模拟截图字节。
        """

        return f"stub-window-capture:{hwnd}".encode("utf-8")

    @staticmethod
    def locate_anchor(anchor_id: str) -> bool:
        """判断锚点是否可定位。"""

        return bool(anchor_id)

    def run_action(
        self,
        action: str,
        target: str | None,
        value: Any | None,
    ) -> ActionOutcome:
        """记录并模拟执行动作。

        Args:
            action: 动作名称。
            target: 目标锚点 ID。
            value: 动作参数。

        Returns:
            动作执行结果。
        """

        self.actions.append((action, target, value))
        if action == "wait":
            self._sleep_for_wait(value)
        anchor_detail = self._anchor_detail(target)
        return ActionOutcome(
            ok=True,
            detail=f"{action} {target or ''}{anchor_detail}".strip(),
            screenshot_path=f"screenshots/{action}_{target or 'na'}.png",
        )

    @staticmethod
    def screenshot(label: str) -> bytes:
        """返回模拟截图字节。"""

        return f"stub-screenshot:{label}".encode("utf-8")

    @staticmethod
    def _sleep_for_wait(value: Any | None) -> None:
        """按等待动作参数短暂休眠。"""

        try:
            duration = float(str(value)) if value is not None else 1.0
        except (TypeError, ValueError):
            duration = 1.0
        time.sleep(max(0.0, duration))

    def _anchor_detail(self, target: str | None) -> str:
        """返回锚点坐标摘要。"""

        if not self._profile or not target:
            return ""
        anchor = next((item for item in self._profile.anchors if item.id == target), None)
        if anchor is None:
            return ""
        roi = anchor.action_region.pixel
        return f" @({roi.x:.0f},{roi.y:.0f},{roi.width:.0f},{roi.height:.0f})"
