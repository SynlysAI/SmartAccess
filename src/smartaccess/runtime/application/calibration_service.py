"""CalibrationService: turn an application UI into a reusable anchor profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartaccess.runtime.application.anchor_service import AnchorService
from smartaccess.runtime.application.ports import (
    AutomationProvider,
    InstrumentProfileDraftGenerator,
    InstrumentReferenceInfo,
    WindowInfo,
)
from smartaccess.runtime.domain.instrument import InstrumentStatus
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract


class CalibrationService:
    """Creates and stores calibrated anchor profiles."""

    def __init__(
        self,
        *,
        automation: AutomationProvider,
        workspace_dir: Path,
        draft_generator: InstrumentProfileDraftGenerator | None = None,
    ) -> None:
        self._automation = automation
        self._workspace_dir = Path(workspace_dir)
        self._draft_generator = draft_generator
        self._last_reasoning = ""
        self._anchors = AnchorService(workspace_dir=self._workspace_dir)
        self._status: dict[str, InstrumentStatus] = {
            profile.profile_id: InstrumentStatus.ACTIVE
            for profile in self._anchors.list_profiles()
        }

    def load_all(self) -> None:
        self._anchors.load_all()

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
    ) -> AnchorsContract:
        """Assemble, persist, and register a calibrated anchor profile."""

        prepared_anchors: list[dict[str, Any]] = []
        for anchor in anchors or []:
            item = dict(anchor)
            if "action_bindings" not in item and "supported_actions" not in item:
                item["main_action"] = item.get("main_action") or "click"
            item["default_wait_seconds"] = float(item.get("default_wait_seconds", 2.0))
            prepared_anchors.append(item)

        profile = self._anchors.create_profile(
            profile_id=device_id,
            title_contains=title_contains,
            anchors=prepared_anchors,
            capture_width=capture_width,
            capture_height=capture_height,
            supported_os=supported_os,
            safety_limits=safety_limits,
        )
        self._status[device_id] = InstrumentStatus.CALIBRATED
        self._write_legacy_instrument_profile(profile)
        return profile

    def draft_profile_from_prompt(self, prompt: str, context: dict[str, Any]) -> AnchorsContract:
        if self._draft_generator is None:
            raise RuntimeError("No instrument draft generator configured")
        profile = self._draft_generator.draft_from_prompt(prompt, context)
        self._last_reasoning = getattr(self._draft_generator, "last_reasoning", "") or ""
        if isinstance(profile, AnchorsContract):
            return profile
        created = self._anchors.create_profile(
            profile_id=profile.device_id,
            title_contains=profile.window_signature.title_contains or "",
            anchors=[
                {
                    "id": anchor.id,
                    "label": anchor.id,
                    "roi": anchor.roi.model_dump(mode="json") if anchor.roi else {},
                    "normalized_roi": (
                        anchor.normalized_roi.model_dump(mode="json")
                        if anchor.normalized_roi
                        else {}
                    ),
                    "action_bindings": [
                        {
                            "action": binding.action,
                            "requires_confirmation": binding.requires_confirmation,
                        }
                        for binding in anchor.action_bindings
                    ],
                    "vision_mode": anchor.vision_mode,
                    "vision_config": (
                        anchor.vision_config.model_dump(mode="json", exclude_none=True)
                        if getattr(anchor, "vision_config", None)
                        and hasattr(anchor.vision_config, "model_dump")
                        else None
                    ),
                    "type": anchor.type,
                }
                for anchor in profile.anchors
            ],
            capture_width=profile.window_signature.capture_width,
            capture_height=profile.window_signature.capture_height,
        )
        created.safety_limits = profile.safety_limits
        created.supported_os = profile.supported_os
        self._write_legacy_instrument_profile(created)
        return created

    def draft_reasoning(self) -> str:
        return self._last_reasoning

    def draft_generator_label(self) -> str:
        if self._draft_generator is None:
            return "Not configured"
        name = type(self._draft_generator).__name__
        return "DeepSeek" if "DeepSeek" in name else "Template"

    def activate(self, device_id: str) -> None:
        if self._anchors.get_profile(device_id):
            self._status[device_id] = InstrumentStatus.ACTIVE

    def status_of(self, device_id: str) -> InstrumentStatus | None:
        return self._status.get(device_id)

    def get_profile(self, device_id: str) -> AnchorsContract | None:
        return self._anchors.get_profile(device_id)

    def list_profiles(self) -> list[AnchorsContract]:
        return self._anchors.list_profiles()

    def delete_instrument(
        self,
        device_id: str,
        *,
        active_sessions: list[str] | None = None,
        force: bool = False,
    ) -> InstrumentReferenceInfo | None:
        if self._anchors.get_profile(device_id) is None:
            return None

        refs = self._check_references(device_id, active_sessions=active_sessions or [])
        if refs.active_session_count > 0:
            raise RuntimeError(
                f"device {device_id} is used by {refs.active_session_count} running sessions"
            )
        if not force and (refs.draft_count > 0 or refs.local_template_count > 0):
            raise RuntimeError(
                f"device {device_id} is referenced by drafts/templates; use force=True to delete"
            )

        self._anchors.delete_profile(device_id)
        legacy_path = self._workspace_dir / "instruments" / device_id
        if legacy_path.exists():
            import shutil

            shutil.rmtree(legacy_path)
        self._status.pop(device_id, None)
        return refs

    def check_instrument_references(
        self,
        device_id: str,
        *,
        active_sessions: list[str] | None = None,
    ) -> InstrumentReferenceInfo:
        return self._check_references(device_id, active_sessions=active_sessions or [])

    def _check_references(
        self,
        device_id: str,
        *,
        active_sessions: list[str],
    ) -> InstrumentReferenceInfo:
        drafts: list[str] = []
        templates: list[str] = []

        for path in sorted((self._workspace_dir / "workflows").glob("*/draft.yaml")):
            try:
                wf = load_yaml_contract(path, type("Wf", (), {"model_validate": lambda d: d}))
            except Exception:
                continue
            if isinstance(wf, dict):
                meta = wf.get("metadata", {})
                if meta.get("anchor_profile") == device_id or meta.get("instrument_profile") == device_id:
                    drafts.append(meta.get("workflow_id", path.parent.name))

        for path in sorted((self._workspace_dir / "templates").glob("*/*/workflow.yaml")):
            try:
                wf = load_yaml_contract(path, type("Wf", (), {"model_validate": lambda d: d}))
            except Exception:
                continue
            if isinstance(wf, dict):
                meta = wf.get("metadata", {})
                if meta.get("anchor_profile") == device_id or meta.get("instrument_profile") == device_id:
                    template_id = meta.get("template_id", path.parent.parent.name)
                    template_version = meta.get("template_version", path.parent.name)
                    templates.append(f"{template_id}@{template_version}")

        return InstrumentReferenceInfo(
            device_id=device_id,
            draft_count=len(drafts),
            local_template_count=len(templates),
            active_session_count=len([session for session in active_sessions if device_id in session]),
            referencing_workflow_ids=drafts or None,
            referencing_template_ids=templates or None,
        )

    def _write_legacy_instrument_profile(self, profile: AnchorsContract) -> None:
        payload = _legacy_instrument_payload(profile)
        legacy = InstrumentProfileContract.model_validate(payload)
        dump_yaml_contract(
            legacy,
            self._workspace_dir / "instruments" / profile.profile_id / "instrument_profile.yaml",
        )


def _coerce_safety_limits(raw: dict[str, Any]):
    class _SafetyLimits:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.requires_manual_confirm_for = list(payload.get("requires_manual_confirm_for") or [])
            self.fields = [
                type("SafetyField", (), field)()
                for field in (payload.get("fields") or [])
            ]

    return _SafetyLimits(raw)


def _legacy_instrument_payload(profile: AnchorsContract) -> dict[str, Any]:
    return {
        "device_id": profile.profile_id,
        "supported_os": profile.supported_os,
        "window_signature": {
            "title_contains": profile.window_signature.title_contains,
            "capture_width": profile.window_signature.capture_width,
            "capture_height": profile.window_signature.capture_height,
        },
        "anchors": [
            {
                "id": anchor.id,
                "type": anchor.type,
                "locator_hint": anchor.locator_hint,
                "roi": anchor.roi.model_dump(mode="json", exclude_none=True),
                "normalized_roi": anchor.normalized_roi.model_dump(mode="json", exclude_none=True),
                "action_bindings": [
                    binding.model_dump(mode="json", exclude_none=True)
                    for binding in anchor.action_bindings
                ],
                "vision_mode": anchor.vision_mode or "none",
                "confidence_threshold": anchor.confidence_threshold,
                "vision_config": (
                    anchor.vision_config.model_dump(mode="json", exclude_none=True)
                    if anchor.vision_config
                    else None
                ),
            }
            for anchor in profile.anchors
        ],
        "actions": profile.actions,
        "safety_limits": profile.safety_limits.model_dump(mode="json", exclude_none=True),
    }
