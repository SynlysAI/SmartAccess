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
from smartaccess.runtime.application.roi_resolver import resolve_anchor_roi
from smartaccess.shared.contracts.instrument_profile import AnchorDefinition, InstrumentProfileContract

from .window_scanner import WindowScanner, capture_window as _capture_real_window, user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002

# -- SendInput structures for Unicode text input --------------------------
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class _INPUT(ctypes.Structure):
    """INPUT structure padded to match Windows sizeof(INPUT) = 40 on 64-bit.

    We only use KEYBDINPUT (24 bytes), but the union's size is dictated by the
    largest member MOUSEINPUT (32 bytes).  Total struct = 4 + 4(pad) + 32 = 40.
    """

    _fields_ = [
        ("type", wintypes.DWORD),
        ("ki", _KEYBDINPUT),
        ("_pad", ctypes.c_ubyte * 8),  # makes sizeof(_INPUT) == 40 on x64
    ]


def _sizeof_input() -> int:
    return ctypes.sizeof(_INPUT)

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
            self._type_text(str(value or ""))
        elif action == "hotkey":
            self._hotkey(str(value or ""))
        elif action == "press_enter":
            self._hotkey("enter")
        elif action == "wait":
            try:
                duration = float(str(value)) if value is not None else 1.0
            except (TypeError, ValueError):
                duration = 1.0
            time.sleep(max(0.0, duration))
        elif action in {"wait_until", "screenshot_check"}:
            # These are orchestration-level actions — the orchestrator handles
            # the observation and polling loop, not the provider.
            return ActionOutcome(ok=True, detail=f"{action} (coordinated by orchestrator)")
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
        width, height = self._window_size()
        roi = resolve_anchor_roi(
            anchor,
            self._profile.window_signature if self._profile else None,
            current_width=width,
            current_height=height,
        )
        if roi is None:
            raise RuntimeError(f"锚点缺少 ROI 坐标: {anchor.id}")
        left, top = self._window_origin()
        rel_x = min(max(roi.x + roi.width / 2, 0), max(width - 1, 0)) if width else roi.x + roi.width / 2
        rel_y = min(max(roi.y + roi.height / 2, 0), max(height - 1, 0)) if height else roi.y + roi.height / 2
        x = int(left + rel_x)
        y = int(top + rel_y)
        user32.SetCursorPos(x, y)
        for _ in range(2 if double else 1):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
            time.sleep(0.05)

    def _window_size(self) -> tuple[int, int]:
        if not self._hwnd:
            return 0, 0
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return max(0, rect.right - rect.left), max(0, rect.bottom - rect.top)

    def _window_origin(self) -> tuple[int, int]:
        if not self._hwnd:
            return 0, 0
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
            return 0, 0
        return rect.left, rect.top

    def _type_text(self, text: str) -> None:
        """Type text using SendInput with KEYEVENTF_UNICODE — handles ASCII and CJK uniformly."""
        user32.SendInput.restype = wintypes.UINT
        n = len(text)
        # Allocate 2 INPUT structs per character (key down + key up)
        inputs = (_INPUT * (n * 2))()
        for i, char in enumerate(text):
            cp = ord(char)
            # Key down
            inputs[i * 2].type = INPUT_KEYBOARD
            inputs[i * 2].ki.wScan = cp
            inputs[i * 2].ki.dwFlags = KEYEVENTF_UNICODE
            # Key up
            inputs[i * 2 + 1].type = INPUT_KEYBOARD
            inputs[i * 2 + 1].ki.wScan = cp
            inputs[i * 2 + 1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        sent = user32.SendInput(n * 2, inputs, ctypes.sizeof(_INPUT))
        if sent != n * 2:
            # Fallback: send one character at a time
            for i in range(n):
                pair = (_INPUT * 2)()
                cp = ord(text[i])
                pair[0].type = INPUT_KEYBOARD
                pair[0].ki.wScan = cp
                pair[0].ki.dwFlags = KEYEVENTF_UNICODE
                pair[1].type = INPUT_KEYBOARD
                pair[1].ki.wScan = cp
                pair[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                user32.SendInput(2, pair, ctypes.sizeof(_INPUT))
                time.sleep(0.01)

    def _hotkey(self, value: str) -> None:
        keys = [part.strip().lower() for part in value.replace("+", ",").split(",") if part.strip()]
        vk_map = {"ctrl": VK_CONTROL, "control": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT, "enter": 0x0D, "tab": 0x09, "esc": 0x1B}
        codes = [vk_map.get(k, ord(k.upper()[0]) if len(k) == 1 else 0) for k in keys]
        codes = [c for c in codes if c]
        for code in codes:
            user32.keybd_event(code, 0, 0, None)
        for code in reversed(codes):
            user32.keybd_event(code, 0, KEYEVENTF_KEYUP, None)
