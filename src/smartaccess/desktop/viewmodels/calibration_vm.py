"""设备接入与校准视图模型。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import WindowInfo
from smartaccess.shared.contracts.anchors import AnchorsContract

from .base import ViewModel


class CalibrationViewModel(ViewModel):
    """校准页和运行时门面之间的适配层。"""

    def discover_windows(self) -> list[WindowInfo]:
        """扫描可接入窗口。"""

        return self._facade.discover_windows()

    def capture_window(self, hwnd: int) -> bytes | None:
        """截取指定窗口。"""

        return self._facade.capture_window(hwnd)

    def list_instruments(self) -> list[AnchorsContract]:
        """列出已保存设备。"""

        return self._facade.list_instruments()

    def get_instrument(self, device_id: str) -> AnchorsContract | None:
        """读取指定设备配置。"""

        return self._facade.get_instrument(device_id)

    def load_instrument_capture(self, device_id: str | None) -> bytes | None:
        """读取指定设备的校准截图。

        Args:
            device_id: 设备 ID。

        Returns:
            PNG 截图字节；不存在时返回 None。
        """

        return self._facade.load_instrument_capture(device_id)

    def workspace_dir(self) -> Path:
        """返回工作区目录。"""

        return self._facade.workspace_dir()

    def ai_label(self) -> str:
        """返回当前 AI 生成器标签。"""

        return self._facade.ai_label()

    def draft_profile(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> AnchorsContract:
        """调用 AI 生成设备锚点草稿。

        Args:
            prompt: 用户描述。
            context: 生成上下文。

        Returns:
            锚点配置草稿。
        """

        profile = self._facade.draft_instrument_from_prompt(prompt, context)
        self.changed.emit()
        return profile

    def ai_reasoning(self) -> str:
        """返回最近一次 AI 生成摘要。"""

        return self._facade.ai_reasoning()

    def delete_instrument(self, device_id: str) -> None:
        """删除设备配置。"""

        self._facade.delete_instrument(device_id)
        self.changed.emit()

    def create_profile(
        self,
        *,
        device_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]],
        capture_width: int | None,
        capture_height: int | None,
        capture_origin_x: int | None = None,
        capture_origin_y: int | None = None,
        capture_data: bytes | None = None,
    ) -> AnchorsContract:
        """创建并保存设备锚点配置。

        Args:
            device_id: 设备 ID。
            title_contains: 窗口标题包含文本。
            anchors: 锚点列表。
            capture_width: 校准截图宽度。
            capture_height: 校准截图高度。
            capture_origin_x: 校准截图画布相对主窗口左侧的 X 偏移。
            capture_origin_y: 校准截图画布相对主窗口顶部的 Y 偏移。
            capture_data: 当前校准截图 PNG 字节。

        Returns:
            保存后的锚点配置。
        """

        profile = self._facade.create_calibration(
            device_id=device_id,
            title_contains=title_contains,
            anchors=anchors,
            capture_width=capture_width,
            capture_height=capture_height,
            capture_origin_x=capture_origin_x,
            capture_origin_y=capture_origin_y,
        )
        if capture_data:
            self._facade.save_instrument_capture(profile.profile_id, capture_data)
        self.changed.emit()
        return profile
