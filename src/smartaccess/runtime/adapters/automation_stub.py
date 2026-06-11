"""Deterministic automation stub with real window scanning.

Stands in for the real Windows GUI automation provider (pywinauto/pyautogui/mss).
Actions are deterministic, while window discovery and capture use the real Win32
API so the calibration page shows the user's actual desktop windows.
"""

from __future__ import annotations

import time
from typing import Any

from smartaccess.runtime.application.ports import ActionOutcome, WindowInfo
from smartaccess.shared.contracts.anchors import AnchorsContract

from .window_scanner import WindowScanner, capture_window as _capture_real_window


class StubAutomationProvider:
    """An always-cooperative automation provider for local runs and tests."""

    def __init__(
        self,
        *,
        window_title: str = "ElectroChem Console",
        use_real_scanner: bool = True,
    ) -> None:
        self._window_title = window_title
        self._scanner = WindowScanner() if use_real_scanner else None
        self._profile: AnchorsContract | None = None
        self.actions: list[tuple[str, str | None, Any]] = []

    def configure_profile(self, profile: AnchorsContract | None) -> None:
        self._profile = profile

    def window_present(self, title_contains: str | None) -> bool:
        if not title_contains:
            return True
        if self._scanner is not None:
            found = self._scanner.scan_contains(title_contains)
            if found:
                return True
        return title_contains.lower() in self._window_title.lower()

    def discover_windows(self) -> list[WindowInfo]:
        if self._scanner is not None:
            raw_windows = self._scanner.scan()
            return [
                WindowInfo(
                    title=rw.title,
                    width=rw.width,
                    height=rw.height,
                    matched=True,
                    hwnd=rw.hwnd,
                )
                for rw in raw_windows
            ]
        return [WindowInfo(title=self._window_title, width=1280, height=860, matched=True)]

    def capture_window(self, hwnd: int) -> bytes | None:
        return _capture_real_window(hwnd)

    def locate_anchor(self, anchor_id: str) -> bool:
        return bool(anchor_id)

    def run_action(self, action: str, target: str | None, value: Any | None) -> ActionOutcome:
        self.actions.append((action, target, value))
        if action == "wait":
            try:
                duration = float(str(value)) if value is not None else 1.0
            except (TypeError, ValueError):
                duration = 1.0
            time.sleep(max(0.0, duration))
        anchor_detail = ""
        if self._profile and target:
            anchor = next((a for a in self._profile.anchors if a.id == target), None)
            if anchor:
                roi = anchor.action_region.pixel
                anchor_detail = f" @({roi.x:.0f},{roi.y:.0f},{roi.width:.0f},{roi.height:.0f})"
        return ActionOutcome(
            ok=True,
            detail=f"{action} {target or ''}{anchor_detail}".strip(),
            screenshot_path=f"screenshots/{action}_{target or 'na'}.png",
        )

    def screenshot(self, label: str) -> bytes:
        return f"stub-screenshot:{label}".encode("utf-8")
