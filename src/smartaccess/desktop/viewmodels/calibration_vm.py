"""Calibration view model: window discovery, capture, and instrument profile creation."""

from __future__ import annotations

from typing import Any

from smartaccess.runtime.application.ports import WindowInfo
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract

from .base import ViewModel


class CalibrationViewModel(ViewModel):
    def discover_windows(self) -> list[WindowInfo]:
        return self._facade.discover_windows()

    def capture_window(self, hwnd: int) -> bytes | None:
        return self._facade.capture_window(hwnd)

    def list_instruments(self) -> list[InstrumentProfileContract]:
        return self._facade.list_instruments()

    def get_instrument(self, device_id: str) -> InstrumentProfileContract | None:
        """Load a specific instrument profile by device_id."""
        return self._facade.get_instrument(device_id)

    def check_references(self, device_id: str):
        """Check how many workflows/templates reference this instrument."""
        return self._facade.check_instrument_references(device_id)

    def delete_instrument(self, device_id: str, *, force: bool = False):
        """Delete an instrument profile after pre-check."""
        return self._facade.delete_instrument(device_id, force=force)

    def create_profile(
        self,
        *,
        device_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]],
        actions: list[str],
        safety_fields: list[dict[str, Any]],
        confirm_steps: list[str],
        capture_width: int | None,
        capture_height: int | None,
    ) -> InstrumentProfileContract:
        safety: dict[str, Any] = {"fields": safety_fields}
        if confirm_steps:
            safety["requires_manual_confirm_for"] = confirm_steps
        profile = self._facade.create_calibration(
            device_id=device_id,
            title_contains=title_contains,
            anchors=anchors,
            actions=actions,
            safety_limits=safety,
            capture_width=capture_width,
            capture_height=capture_height,
        )
        self.changed.emit()
        return profile
