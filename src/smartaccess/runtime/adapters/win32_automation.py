"""基于 Win32 API 的轻量 UI 自动化适配器。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from smartaccess.runtime.application.ports import ActionOutcome, WindowInfo
from smartaccess.runtime.application.roi_resolver import resolve_anchor_roi
from smartaccess.shared.contracts.anchors import AnchorDefinition, AnchorsContract

from .window_scanner import WindowScanner, capture_window as _capture_real_window

SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
GW_ENABLEDPOPUP = 6


class _KeybdInput(ctypes.Structure):
    """Win32 KEYBDINPUT 结构。"""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class _Input(ctypes.Structure):
    """Win32 INPUT 结构。"""

    _fields_ = [
        ("type", wintypes.DWORD),
        ("ki", _KeybdInput),
        ("_pad", ctypes.c_ubyte * 8),
    ]


class Win32AutomationProvider:
    """面向 Windows 桌面软件的真实自动化提供者。"""

    def __init__(self) -> None:
        """初始化 Win32 自动化提供者。"""

        self._user32 = ctypes.windll.user32
        self._configure_api()
        self._scanner = WindowScanner()
        self._profile: AnchorsContract | None = None
        self._hwnd: int | None = None

    def configure_profile(self, profile: AnchorsContract | None) -> None:
        """配置当前锚点配置。

        Args:
            profile: 当前锚点配置。
        """

        self._profile = profile
        title = profile.window_signature.title_contains if profile else None
        self._hwnd = self._find_hwnd(title)

    def window_present(self, title_contains: str | None) -> bool:
        """判断目标窗口是否存在。"""

        self._hwnd = self._find_hwnd(title_contains)
        return self._hwnd is not None

    def discover_windows(self) -> list[WindowInfo]:
        """扫描当前桌面窗口。"""

        return [
            WindowInfo(
                title=window.title,
                width=window.width,
                height=window.height,
                matched=True,
                hwnd=window.hwnd,
            )
            for window in self._scanner.scan()
        ]

    @staticmethod
    def capture_window(hwnd: int) -> bytes | None:
        """按句柄截取窗口图像。"""

        Win32AutomationProvider._restore_and_focus_window(hwnd)
        return _capture_real_window(hwnd)

    def locate_anchor(self, anchor_id: str) -> bool:
        """判断锚点是否存在于当前配置。"""

        return self._anchor(anchor_id) is not None

    def run_action(
        self,
        action: str,
        target: str | None,
        value: Any | None,
    ) -> ActionOutcome:
        """执行一个自动化动作。

        Args:
            action: 动作名称。
            target: 目标锚点 ID。
            value: 动作参数。

        Returns:
            动作执行结果。
        """

        anchor = self._anchor(target) if target else None
        if target and anchor is None:
            return ActionOutcome(ok=False, detail=f"未找到锚点: {target}")
        if self._hwnd:
            self._focus_interaction_window()
        try:
            self._dispatch_action(action, anchor, value)
        except Exception as exc:  # noqa: BLE001 - 自动化错误需返回给运行层
            return ActionOutcome(ok=False, detail=str(exc))
        return ActionOutcome(ok=True, detail=f"{action} {target or ''}".strip())

    def screenshot(self, label: str) -> bytes:
        """截取当前目标窗口图像。"""

        if self._hwnd is None:
            return b""
        self._focus_interaction_window()
        return _capture_real_window(self._hwnd) or b""

    def _configure_api(self) -> None:
        """配置 Win32 输入 API。"""

        self._user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self._user32.SetCursorPos.restype = wintypes.BOOL
        self._user32.mouse_event.argtypes = (
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        self._user32.keybd_event.argtypes = (
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
        self._user32.GetWindow.restype = wintypes.HWND

    def _find_hwnd(self, title_contains: str | None) -> int | None:
        """查找目标窗口句柄。"""

        if not title_contains:
            windows = self._scanner.scan()
        elif self._profile is not None and self._profile.window_signature.match_mode == "equals":
            windows = self._scanner.scan_equals(title_contains)
        else:
            windows = self._scanner.scan_contains(title_contains)
        return windows[0].hwnd if windows else None

    @staticmethod
    def _restore_and_focus_window(hwnd: int) -> None:
        """还原并前置指定窗口。

        Args:
            hwnd: 目标窗口句柄。
        """

        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)

    def _restore_window(self, hwnd: int) -> None:
        """还原最小化的窗口。

        Args:
            hwnd: 目标窗口句柄。
        """

        if self._user32.IsIconic(hwnd):
            self._user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)

    def _focus_interaction_window(self) -> int | None:
        """前置当前交互窗口，弹窗存在时优先前置弹窗。

        Returns:
            当前用于接收输入的窗口句柄。
        """

        if self._hwnd is None:
            return None
        self._restore_window(self._hwnd)
        target_hwnd = self._active_popup_hwnd(self._hwnd) or self._hwnd
        self._user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.1)
        return target_hwnd

    def _active_popup_hwnd(self, hwnd: int) -> int | None:
        """返回目标窗口当前可用弹窗句柄。

        Args:
            hwnd: 主窗口句柄。

        Returns:
            可见且可用的弹窗句柄；不存在时返回 None。
        """

        popup_hwnd = self._user32.GetWindow(hwnd, GW_ENABLEDPOPUP)
        if not popup_hwnd or popup_hwnd == hwnd:
            return None
        if not self._user32.IsWindowVisible(popup_hwnd):
            return None
        if not self._user32.IsWindowEnabled(popup_hwnd):
            return None
        return int(popup_hwnd)

    def _anchor(self, anchor_id: str | None) -> AnchorDefinition | None:
        """按 ID 查找锚点。"""

        if not anchor_id or self._profile is None:
            return None
        return next(
            (anchor for anchor in self._profile.anchors if anchor.id == anchor_id),
            None,
        )

    def _dispatch_action(
        self,
        action: str,
        anchor: AnchorDefinition | None,
        value: Any | None,
    ) -> None:
        """分发具体动作。"""

        if action == "click" and anchor is not None:
            self._click_anchor(anchor)
        elif action == "type":
            self._type_text(str(value or ""))
        elif action == "hotkey":
            self._hotkey(str(value or ""))
        elif action == "press_enter":
            self._hotkey("enter")
        elif action == "wait":
            self._wait(value)
        else:
            raise RuntimeError(f"不支持的动作: {action}")

    def _click_anchor(self, anchor: AnchorDefinition) -> None:
        """点击锚点中心位置。"""

        width, height = self._capture_reference_size()
        roi = resolve_anchor_roi(
            anchor,
            self._profile.window_signature if self._profile else None,
            current_width=width,
            current_height=height,
        )
        if roi is None:
            raise RuntimeError(f"锚点缺少 ROI 坐标: {anchor.id}")
        left, top = self._window_origin()
        rel_x = roi.x + roi.width / 2
        rel_y = roi.y + roi.height / 2
        if width:
            rel_x = min(max(rel_x, 0), max(width - 1, 0))
        if height:
            rel_y = min(max(rel_y, 0), max(height - 1, 0))
        offset_x, offset_y = self._capture_origin_offset()
        self._user32.SetCursorPos(int(left + rel_x - offset_x), int(top + rel_y - offset_y))
        self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
        self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)

    def _capture_reference_size(self) -> tuple[int, int]:
        """返回用于解析锚点坐标的参考截图尺寸。"""

        signature = self._profile.window_signature if self._profile else None
        if signature and signature.capture_width and signature.capture_height:
            return signature.capture_width, signature.capture_height
        return self._window_size()

    def _capture_origin_offset(self) -> tuple[int, int]:
        """返回校准截图原点相对当前主窗口的偏移。

        Returns:
            X、Y 方向偏移；无历史元数据时为 0。
        """

        if not self._profile or not self._hwnd:
            return 0, 0
        signature = self._profile.window_signature
        capture_origin_x = int(getattr(signature, "capture_origin_x", 0) or 0)
        capture_origin_y = int(getattr(signature, "capture_origin_y", 0) or 0)
        return capture_origin_x, capture_origin_y

    def _window_size(self) -> tuple[int, int]:
        """返回当前目标窗口尺寸。"""

        if not self._hwnd:
            return 0, 0
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return max(0, rect.right - rect.left), max(0, rect.bottom - rect.top)

    def _window_origin(self) -> tuple[int, int]:
        """返回当前目标窗口左上角坐标。"""

        if not self._hwnd:
            return 0, 0
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return rect.left, rect.top

    def _type_text(self, text: str) -> None:
        """通过 SendInput 输入 Unicode 文本。"""

        if not text:
            return
        inputs = (_Input * (len(text) * 2))()
        for index, char in enumerate(text):
            codepoint = ord(char)
            inputs[index * 2].type = INPUT_KEYBOARD
            inputs[index * 2].ki.wScan = codepoint
            inputs[index * 2].ki.dwFlags = KEYEVENTF_UNICODE
            inputs[index * 2 + 1].type = INPUT_KEYBOARD
            inputs[index * 2 + 1].ki.wScan = codepoint
            inputs[index * 2 + 1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        self._user32.SendInput(len(text) * 2, inputs, ctypes.sizeof(_Input))

    def _hotkey(self, value: str) -> None:
        """发送热键。"""

        keys = [
            part.strip().lower()
            for part in value.replace("+", ",").split(",")
            if part.strip()
        ]
        vk_map = {
            "ctrl": VK_CONTROL,
            "control": VK_CONTROL,
            "alt": VK_MENU,
            "shift": VK_SHIFT,
            "enter": 0x0D,
            "tab": 0x09,
            "esc": 0x1B,
        }
        codes = [
            vk_map.get(key, ord(key.upper()[0]) if len(key) == 1 else 0)
            for key in keys
        ]
        codes = [code for code in codes if code]
        for code in codes:
            self._user32.keybd_event(code, 0, 0, None)
        for code in reversed(codes):
            self._user32.keybd_event(code, 0, KEYEVENTF_KEYUP, None)

    @staticmethod
    def _wait(value: Any | None) -> None:
        """执行固定等待。"""

        try:
            duration = float(str(value)) if value is not None else 1.0
        except (TypeError, ValueError):
            duration = 1.0
        time.sleep(max(0.0, duration))
