"""Real-ish Windows automation provider using Win32 APIs.

This provider intentionally stays small and dependency-free. It reuses the
project's existing Win32 scanner/capture helpers, sends mouse/keyboard input via
user32, and resolves anchors from calibrated ROI coordinates.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from smartaccess.runtime.application.ports import ActionOutcome, WindowInfo
from smartaccess.shared.contracts.instrument_profile import AnchorDefinition, InstrumentProfileContract

from .window_scanner import WindowScanner, capture_window as _capture_real_window, user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002

user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.mouse_event.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
user32.mouse_event.restype = None
user32.keybd_event.argtypes = (wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p)
user32.keybd_event.restype = None


class Win32AutomationProvider:
    """AutomationProvider implementation for simple Windows UI actions."""

    def __init__(self) -> None:
        self._scanner = WindowScanner()
        self._profile: InstrumentProfileContract | None = None
        self._hwnd: int | None = None

    def configure_profile(self, profile: InstrumentProfileContract | None) -> None:
        self._profile = profile
        self._hwnd = self._find_hwnd(profile.window_signature.title_contains if profile else None)

    def window_present(self, title_contains: str | None) -> bool:
        self._hwnd = self._find_hwnd(title_contains)
        return self._hwnd is not None

    def discover_windows(self) -> list[WindowInfo]:
        return [
            WindowInfo(title=w.title, width=w.width, height=w.height, matched=True, hwnd=w.hwnd)
            for w in self._scanner.scan()
        ]

    def capture_window(self, hwnd: int) -> bytes | None:
        return _capture_real_window(hwnd)

    def locate_anchor(self, anchor_id: str) -> bool:
        return self._anchor(anchor_id) is not None

    def run_action(self, action: str, target: str | None, value: Any | None) -> ActionOutcome:
        anchor = self._anchor(target) if target else None
        if target and anchor is None:
            return ActionOutcome(ok=False, detail=f"未找到锚点: {target}")
        if self._hwnd:
            user32.SetForegroundWindow(self._hwnd)
            time.sleep(0.1)
        if action in {"click", "double_click"} and anchor is not None:
            self._click_anchor(anchor, double=(action == "double_click"))
        elif action == "type":
            if anchor is not None:
                self._click_anchor(anchor)
            self._type_text(str(value or ""))
        elif action == "hotkey":
            self._hotkey(str(value or ""))
        elif action in {"wait", "wait_until", "screenshot_check"}:
            time.sleep(0.2)
        else:
            return ActionOutcome(ok=False, detail=f"不支持的动作: {action}")
        return ActionOutcome(ok=True, detail=f"{action} {target or ''}".strip())

    def screenshot(self, label: str) -> bytes:
        if self._hwnd is None:
            return b""
        return _capture_real_window(self._hwnd) or b""

    def _find_hwnd(self, title_contains: str | None) -> int | None:
        windows = self._scanner.scan_contains(title_contains) if title_contains else self._scanner.scan()
        return windows[0].hwnd if windows else None

    def _anchor(self, anchor_id: str | None) -> AnchorDefinition | None:
        if not anchor_id or self._profile is None:
            return None
        return next((a for a in self._profile.anchors if a.id == anchor_id), None)

    def _click_anchor(self, anchor: AnchorDefinition, *, double: bool = False) -> None:
        if anchor.roi is None:
            raise RuntimeError(f"锚点缺少 ROI 坐标: {anchor.id}")
        left, top = self._window_origin()
        x = int(left + anchor.roi.x + anchor.roi.width / 2)
        y = int(top + anchor.roi.y + anchor.roi.height / 2)
        user32.SetCursorPos(x, y)
        for _ in range(2 if double else 1):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
            time.sleep(0.05)

    def _window_origin(self) -> tuple[int, int]:
        if not self._hwnd:
            return 0, 0
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return rect.left, rect.top

    def _type_text(self, text: str) -> None:
        for char in text:
            user32.VkKeyScanW.restype = ctypes.c_short
            vk = user32.VkKeyScanW(ord(char)) & 0xFF
            if vk:
                user32.keybd_event(vk, 0, 0, None)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, None)
                time.sleep(0.02)

    def _hotkey(self, value: str) -> None:
        keys = [part.strip().lower() for part in value.replace("+", ",").split(",") if part.strip()]
        vk_map = {"ctrl": VK_CONTROL, "control": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT, "enter": 0x0D, "tab": 0x09, "esc": 0x1B}
        codes = [vk_map.get(k, ord(k.upper()[0]) if len(k) == 1 else 0) for k in keys]
        codes = [c for c in codes if c]
        for code in codes:
            user32.keybd_event(code, 0, 0, None)
        for code in reversed(codes):
            user32.keybd_event(code, 0, KEYEVENTF_KEYUP, None)
