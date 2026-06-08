"""CalibrationService: turn an instrument UI into a reusable profile.

Drives window discovery through the :class:`AutomationProvider` port, assembles
an ``instrument_profile.yaml`` contract, persists it under the workspace, and
tracks the instrument lifecycle state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import AutomationProvider, WindowInfo
from smartaccess.runtime.domain.instrument import InstrumentStatus
from smartaccess.shared.contracts.instrument_profile import (
    AnchorDefinition,
    InstrumentProfileContract,
    SafetyLimits,
    WindowSignature,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract


class CalibrationService:
    """Creates and stores calibrated instrument profiles."""

    def __init__(self, *, automation: AutomationProvider, workspace_dir: Path) -> None:
        self._automation = automation
        self._workspace_dir = Path(workspace_dir)
        self._profiles: dict[str, InstrumentProfileContract] = {}
        self._status: dict[str, InstrumentStatus] = {}
        self.load_all()

    def load_all(self) -> None:
        """Load every saved instrument profile under the workspace."""

        for path in sorted((self._workspace_dir / "instruments").glob("*/instrument_profile.yaml")):
            try:
                profile = load_yaml_contract(path, InstrumentProfileContract)
            except Exception:
                continue
            self._profiles[profile.device_id] = profile
            self._status.setdefault(profile.device_id, InstrumentStatus.ACTIVE)

    def discover_windows(self) -> list[WindowInfo]:
        return self._automation.discover_windows()

    def capture_window(self, hwnd: int) -> bytes | None:
        return self._automation.capture_window(hwnd)

    def create_profile(
        self,
        *,
        device_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]] | None = None,
        actions: list[str] | None = None,
        safety_limits: dict[str, Any] | None = None,
        supported_os: list[str] | None = None,
        capture_width: int | None = None,
        capture_height: int | None = None,
    ) -> InstrumentProfileContract:
        """Assemble, persist, and register a calibrated instrument profile."""

        profile = InstrumentProfileContract(
            device_id=device_id,
            supported_os=supported_os or ["windows"],
            window_signature=WindowSignature(
                title_contains=title_contains,
                capture_width=capture_width,
                capture_height=capture_height,
            ),
            anchors=[AnchorDefinition(**a) for a in (anchors or [])],
            actions=actions or ["click", "type", "hotkey", "wait_until"],
            safety_limits=SafetyLimits(**(safety_limits or {})),
        )
        self._profiles[device_id] = profile
        self._status[device_id] = InstrumentStatus.CALIBRATED
        dump_yaml_contract(profile, self._profile_path(device_id))
        return profile

    def activate(self, device_id: str) -> None:
        if device_id in self._profiles:
            self._status[device_id] = InstrumentStatus.ACTIVE

    def status_of(self, device_id: str) -> InstrumentStatus | None:
        return self._status.get(device_id)

    def get_profile(self, device_id: str) -> InstrumentProfileContract | None:
        return self._profiles.get(device_id)

    def list_profiles(self) -> list[InstrumentProfileContract]:
        return list(self._profiles.values())

    def _profile_path(self, device_id: str) -> Path:
        return (
            self._workspace_dir
            / "instruments"
            / device_id
            / "instrument_profile.yaml"
        )
