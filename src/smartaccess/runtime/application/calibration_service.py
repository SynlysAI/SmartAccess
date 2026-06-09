"""CalibrationService: turn an instrument UI into a reusable profile.

Drives window discovery through the :class:`AutomationProvider` port, assembles
an ``instrument_profile.yaml`` contract, persists it under the workspace, and
tracks the instrument lifecycle state.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import (
    AutomationProvider,
    InstrumentReferenceInfo,
    WindowInfo,
)
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

    def delete_instrument(self, device_id: str, *, active_sessions: list[str] | None = None, force: bool = False) -> InstrumentReferenceInfo | None:
        """Delete an instrument profile and its YAML file.

        Returns the reference info used for the pre-check decision, or ``None``
        when the profile did not exist.
        """
        if device_id not in self._profiles:
            return None

        refs = self._check_references(device_id, active_sessions=active_sessions or [])

        # Block if any active session is using this instrument
        if refs.active_session_count > 0:
            raise RuntimeError(
                f"仪器 {device_id} 正被 {refs.active_session_count} 个运行中 session 使用，无法删除。"
                f"请先停止相关运行。"
            )

        if not force and (refs.draft_count > 0 or refs.local_template_count > 0):
            raise RuntimeError(
                f"仪器 {device_id} 被 {refs.draft_count} 个本地草稿和 "
                f"{refs.local_template_count} 个本地模板引用。"
                f"请使用 force=True 确认删除（不级联删除工作流/模板）。"
            )

        # Remove from disk
        profile_dir = self._profile_path(device_id).parent
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

        # Remove from memory
        del self._profiles[device_id]
        self._status.pop(device_id, None)

        return refs

    def check_instrument_references(self, device_id: str, *, active_sessions: list[str] | None = None) -> InstrumentReferenceInfo:
        """Return reference counts for a pre-delete pre-check display."""
        return self._check_references(device_id, active_sessions=active_sessions or [])

    def _check_references(self, device_id: str, *, active_sessions: list[str]) -> InstrumentReferenceInfo:
        """Scan local workspace for references to *device_id*."""
        drafts: list[str] = []
        templates: list[str] = []

        # Scan local workflow drafts
        for path in sorted((self._workspace_dir / "workflows").glob("*/draft.yaml")):
            try:
                wf = load_yaml_contract(path, type("Wf", (), {"model_validate": lambda d: d}))  # noqa: SIM115
                if isinstance(wf, dict):
                    meta = wf.get("metadata", {})
                    if meta.get("instrument_profile") == device_id:
                        drafts.append(meta.get("workflow_id", path.parent.name))
            except Exception:
                continue

        # Scan local templates
        for path in sorted((self._workspace_dir / "templates").glob("*/*/workflow.yaml")):
            try:
                wf = load_yaml_contract(path, type("Wf", (), {"model_validate": lambda d: d}))  # noqa: SIM115
                if isinstance(wf, dict):
                    meta = wf.get("metadata", {})
                    if meta.get("instrument_profile") == device_id:
                        tid = meta.get("template_id", path.parent.parent.name)
                        tver = meta.get("template_version", path.parent.name)
                        templates.append(f"{tid}@{tver}")
            except Exception:
                continue

        return InstrumentReferenceInfo(
            device_id=device_id,
            draft_count=len(drafts),
            local_template_count=len(templates),
            active_session_count=len([s for s in active_sessions if device_id in s]),
            referencing_workflow_ids=drafts if drafts else None,
            referencing_template_ids=templates if templates else None,
        )

    def _profile_path(self, device_id: str) -> Path:
        return (
            self._workspace_dir
            / "instruments"
            / device_id
            / "instrument_profile.yaml"
        )
