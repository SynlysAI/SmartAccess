"""AnchorService: load, create, persist, and query anchor profiles."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from smartaccess.shared.contracts.anchors import (
    ACTION_SUPPORT_SETS,
    AnchorActionBinding,
    AnchorDefinition,
    AnchorRegion,
    AnchorsContract,
    NormalizedRegion,
    PixelRegion,
    SIMPLIFIED_ACTIONS,
    WindowSignature,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract


class AnchorService:
    """Owns workspace anchor profiles under ``workspace/anchors``."""

    def __init__(self, *, workspace_dir: Path) -> None:
        self._workspace_dir = Path(workspace_dir)
        self._profiles: dict[str, AnchorsContract] = {}
        self.load_all()

    def load_all(self) -> None:
        self._profiles.clear()
        for path in sorted((self._workspace_dir / "anchors").glob("*/anchors.yaml")):
            try:
                profile = load_yaml_contract(path, AnchorsContract)
            except Exception:
                continue
            self._profiles[profile.profile_id] = profile

    def create_profile(
        self,
        *,
        profile_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]] | None = None,
        process_name: str | None = None,
        capture_width: int | None = None,
        capture_height: int | None = None,
        supported_os: list[str] | None = None,
        safety_limits: dict[str, Any] | None = None,
    ) -> AnchorsContract:
        profile = AnchorsContract(
            profile_id=profile_id,
            window_signature=WindowSignature(
                title_contains=title_contains,
                process_name=process_name,
                screenshot_size={
                    "width": capture_width,
                    "height": capture_height,
                },
            ),
            anchors=[self._coerce_anchor(anchor) for anchor in (anchors or [])],
            supported_os=supported_os or ["windows"],
            safety_limits=safety_limits or {},
        )
        self._profiles[profile_id] = profile
        dump_yaml_contract(profile, self._profile_path(profile_id))
        return profile

    def get_profile(self, profile_id: str | None) -> AnchorsContract | None:
        if not profile_id:
            return None
        return self._profiles.get(profile_id)

    def list_profiles(self) -> list[AnchorsContract]:
        return list(self._profiles.values())

    def delete_profile(self, profile_id: str) -> None:
        if profile_id in self._profiles:
            del self._profiles[profile_id]
        path = self._profile_path(profile_id)
        if path.parent.exists():
            shutil.rmtree(path.parent)

    def _profile_path(self, profile_id: str) -> Path:
        return self._workspace_dir / "anchors" / profile_id / "anchors.yaml"

    @staticmethod
    def _coerce_anchor(raw: dict[str, Any]) -> AnchorDefinition:
        if "action_region" in raw:
            return AnchorService._simplify_anchor(AnchorDefinition.model_validate(raw))

        roi = raw.get("roi") or {}
        normalized = raw.get("normalized_roi") or {}
        action_bindings = raw.get("action_bindings") or []
        main_action = raw.get("main_action")
        if not main_action and action_bindings:
            main_action = action_bindings[0].get("action")
        if main_action not in SIMPLIFIED_ACTIONS:
            main_action = "click"
        supported_actions = ACTION_SUPPORT_SETS[main_action]
        requires_confirmation = bool(raw.get("requires_confirmation"))
        if action_bindings:
            requires_confirmation = any(
                bool(binding.get("requires_confirmation")) for binding in action_bindings
            )
        simplified_bindings = [
            {"action": action, "requires_confirmation": requires_confirmation}
            for action in supported_actions
        ]
        observe_roi = raw.get("observe_roi") or raw.get("observe_region")
        observe_normalized = raw.get("observe_normalized_roi")
        vision_mode = raw.get("vision_mode") or ("ocr" if observe_roi else "none")
        observe_region = None
        if vision_mode == "ocr":
            observe_pixel = observe_roi.get("pixel") if isinstance(observe_roi, dict) and "pixel" in observe_roi else observe_roi or roi
            observe_norm = (
                observe_roi.get("normalized")
                if isinstance(observe_roi, dict) and "normalized" in observe_roi
                else observe_normalized or normalized
            )
            observe_region = AnchorRegion(
                pixel=PixelRegion(**(observe_pixel or {})),
                normalized=NormalizedRegion(**(observe_norm or {})) if observe_norm else NormalizedRegion(),
            )
        return AnchorService._simplify_anchor(AnchorDefinition(
            id=raw["id"],
            label=raw.get("label") or raw["id"],
            action_region=AnchorRegion(
                pixel=PixelRegion(**roi),
                normalized=NormalizedRegion(**normalized) if normalized else NormalizedRegion(),
            ),
            observe_region=observe_region,
            supported_actions=supported_actions,
            default_wait_seconds=float(raw.get("default_wait_seconds", 2.0)),
            notes=raw.get("notes"),
            type=raw.get("type"),
            locator_hint=raw.get("locator_hint"),
            vision_mode=vision_mode,
            action_bindings=simplified_bindings,
            roi=roi,
            normalized_roi=normalized,
        ))

    @staticmethod
    def _simplify_anchor(anchor: AnchorDefinition) -> AnchorDefinition:
        supported_actions = [
            action for action in anchor.supported_actions if action in SIMPLIFIED_ACTIONS
        ] or ["click"]
        requires_confirmation = any(
            binding.requires_confirmation
            for binding in anchor.action_bindings
            if binding.action in supported_actions
        )
        anchor.supported_actions = list(dict.fromkeys(supported_actions))
        anchor.action_bindings = [
            AnchorActionBinding(action=action, requires_confirmation=requires_confirmation)
            for action in anchor.supported_actions
        ]
        anchor.type = "observation" if anchor.observe_region is not None else "action_target"
        anchor.vision_mode = "ocr" if anchor.observe_region is not None else None
        anchor.confidence_threshold = None
        anchor.vision_config = None
        return anchor
