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

    def capture_windows(self, hwnds: list[int]) -> bytes | None:
        """截取多个窗口的屏幕联合区域。

        Args:
            hwnds: 窗口句柄列表。

        Returns:
            PNG 截图字节；失败时返回 None。
        """

        return self._facade.capture_windows(hwnds)

    def list_instruments(self) -> list[AnchorsContract]:
        """列出已保存设备。"""

        return self._facade.list_instruments()

    def get_instrument(self, device_id: str) -> AnchorsContract | None:
        """读取指定设备配置。"""

        return self._facade.get_instrument(device_id)

    def load_instrument_capture(
        self,
        device_id: str | None,
        *,
        view_id: str | None = None,
    ) -> bytes | None:
        """读取指定设备的校准截图。

        Args:
            device_id: 设备 ID。

        Returns:
            PNG 截图字节；不存在时返回 None。
        """

        return self._facade.load_instrument_capture(device_id, view_id=view_id)

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
        views: list[dict[str, Any]] | None = None,
        capture_width: int | None,
        capture_height: int | None,
        capture_origin_x: int | None = None,
        capture_origin_y: int | None = None,
        capture_mode: str = "window",
        capture_screen_origin_x: int | None = None,
        capture_screen_origin_y: int | None = None,
        capture_windows: list[dict[str, Any]] | None = None,
        capture_data: bytes | None = None,
        view_captures: dict[str, bytes] | None = None,
    ) -> AnchorsContract:
        """创建并保存设备锚点配置。

        Args:
            device_id: 设备 ID。
            title_contains: 窗口标题包含文本。
            anchors: 锚点列表。
            capture_width: 校准截图宽度。
            capture_height: 校准截图高度。
            capture_origin_x: 兼容旧窗口模式的截图原点 X 偏移。
            capture_origin_y: 兼容旧窗口模式的截图原点 Y 偏移。
            capture_mode: 截图坐标模式。
            capture_screen_origin_x: 校准截图画布在屏幕上的左上角 X。
            capture_screen_origin_y: 校准截图画布在屏幕上的左上角 Y。
            capture_windows: 参与截图的窗口元数据。
            capture_data: 当前校准截图 PNG 字节。

        Returns:
            保存后的锚点配置。
        """

        profile = self._facade.create_calibration(
            device_id=device_id,
            title_contains=title_contains,
            anchors=anchors,
            views=views,
            capture_width=capture_width,
            capture_height=capture_height,
            capture_origin_x=capture_origin_x,
            capture_origin_y=capture_origin_y,
            capture_mode=capture_mode,
            capture_screen_origin_x=capture_screen_origin_x,
            capture_screen_origin_y=capture_screen_origin_y,
            capture_windows=capture_windows,
        )
        if capture_data:
            self._facade.save_instrument_capture(profile.profile_id, capture_data)
        for view_id, data in (view_captures or {}).items():
            if data:
                self._facade.save_instrument_capture(
                    profile.profile_id,
                    data,
                    view_id=view_id,
                )
        self.changed.emit()
        return profile

    def preview_anchor_ocr(
        self,
        *,
        capture_data: bytes,
        anchor_payload: dict[str, Any],
    ) -> str:
        """对当前校准截图中的锚点执行一次 OCR 预览。"""

        reading = self._facade.preview_anchor_ocr(
            capture_data=capture_data,
            anchor_payload=anchor_payload,
        )
        return reading.text
