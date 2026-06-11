"""Pydantic models for `anchors.yaml`."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, FlexibleContractModel, NonEmptyStr
from .instrument_profile import SafetyLimits, VisionConfig

SIMPLIFIED_ACTIONS: tuple[str, ...] = ("click", "type", "hotkey", "press_enter")
ACTION_SUPPORT_SETS: dict[str, list[str]] = {
    "click": ["click"],
    "type": ["click", "type", "hotkey", "press_enter"],
    "hotkey": ["click", "hotkey"],
    "press_enter": ["click", "press_enter"],
}
LEGACY_ANCHOR_TYPES = {
    "action_target",
    "observation",
    "button",
    "input",
    "readout",
    "status",
    "region",
    "roi",
}


class ScreenshotSize(FlexibleContractModel):
    """Reference screenshot size used when the anchor profile was captured."""

    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)


class WindowSignature(FlexibleContractModel):
    """Window hints used to find the target application."""

    title_contains: str | None = None
    process_name: str | None = None
    screenshot_size: ScreenshotSize | None = None

    @property
    def capture_width(self) -> int | None:
        return self.screenshot_size.width if self.screenshot_size else None

    @property
    def capture_height(self) -> int | None:
        return self.screenshot_size.height if self.screenshot_size else None


class PixelRegion(FlexibleContractModel):
    """Region in screenshot pixel coordinates."""

    x: float = Field(default=0, ge=0)
    y: float = Field(default=0, ge=0)
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)


class NormalizedRegion(FlexibleContractModel):
    """Region normalized to the screenshot dimensions."""

    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=0, ge=0, le=1)
    height: float = Field(default=0, ge=0, le=1)


class AnchorRegion(FlexibleContractModel):
    """A region stored in both pixel and normalized coordinates."""

    pixel: PixelRegion
    normalized: NormalizedRegion


class AnchorActionBinding(FlexibleContractModel):
    """A simplified action binding stored in `anchors.yaml`."""

    action: NonEmptyStr
    requires_confirmation: bool = False


class AnchorDefinition(FlexibleContractModel):
    """A UI anchor with an action area and optional OCR observation area."""

    id: NonEmptyStr
    label: str | None = Field(default=None, exclude=True)
    action_region: AnchorRegion
    observe_region: AnchorRegion | None = None
    supported_actions: list[NonEmptyStr] = Field(default_factory=list)
    default_wait_seconds: float = Field(default=2.0, ge=0)
    notes: str | None = None
    type: str | None = Field(default=None, exclude=True)
    locator_hint: str | None = Field(default=None, exclude=True)
    roi: PixelRegion | None = Field(default=None, exclude=True)
    normalized_roi: NormalizedRegion | None = Field(default=None, exclude=True)
    action_bindings: list[AnchorActionBinding] = Field(default_factory=list)
    vision_mode: Literal["ocr", "template", "presence", "color", "none"] | None = None
    confidence_threshold: float | None = Field(default=None, ge=0, le=1, exclude=True)
    vision_config: VisionConfig | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_shape(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "action_region" not in data:
            roi = data.get("roi") or {}
            normalized = data.get("normalized_roi") or {}
            data["action_region"] = {
                "pixel": roi,
                "normalized": normalized,
            }
        if "observe_region" not in data:
            vision_mode = data.get("vision_mode") or "none"
            legacy_type = data.get("type")
            if vision_mode == "ocr" or legacy_type in {"observation", "readout", "status", "region", "roi"}:
                observe_roi = data.get("observe_roi") or data.get("roi") or {}
                observe_normalized = data.get("observe_normalized_roi") or data.get("normalized_roi") or {}
                data["observe_region"] = {
                    "pixel": observe_roi,
                    "normalized": observe_normalized,
                }
        if "label" not in data and data.get("id"):
            data["label"] = data["id"]
        return data

    @model_validator(mode="after")
    def _normalize_compat_fields(self) -> "AnchorDefinition":
        if self.label is None:
            self.label = self.id
        if self.roi is None:
            self.roi = self.action_region.pixel
        if self.normalized_roi is None:
            self.normalized_roi = self.action_region.normalized
        self.supported_actions = [
            action for action in self.supported_actions if action in SIMPLIFIED_ACTIONS
        ]
        if not self.action_bindings and self.supported_actions:
            self.action_bindings = [
                AnchorActionBinding(action=action, requires_confirmation=False)
                for action in self.supported_actions
            ]
        if not self.supported_actions and self.action_bindings:
            self.supported_actions = [
                binding.action
                for binding in self.action_bindings
                if binding.action in SIMPLIFIED_ACTIONS
            ]
        self.supported_actions = [
            action for action in dict.fromkeys(self.supported_actions) if action in SIMPLIFIED_ACTIONS
        ]
        self.action_bindings = [
            binding
            for binding in self.action_bindings
            if binding.action in SIMPLIFIED_ACTIONS
        ]
        if not self.supported_actions:
            self.supported_actions = ["click"]
        requires_confirmation = any(
            binding.requires_confirmation for binding in self.action_bindings
        )
        self.action_bindings = [
            AnchorActionBinding(
                action=action,
                requires_confirmation=requires_confirmation,
            )
            for action in self.supported_actions
        ]
        if self.type is None:
            self.type = "observation" if self.observe_region is not None else "action_target"
        if self.observe_region is not None and self.vision_mode in (None, "none"):
            self.vision_mode = "ocr"
        if self.observe_region is None:
            self.vision_mode = None
        return self


class AnchorsContract(ContractModel):
    """Top-level contract for SmartAccess anchor profiles."""

    profile_id: NonEmptyStr
    window_signature: WindowSignature
    anchors: list[AnchorDefinition] = Field(default_factory=list)
    supported_os: list[NonEmptyStr] = Field(default_factory=list, exclude=True)
    safety_limits: SafetyLimits = Field(default_factory=SafetyLimits, exclude=True)

    @model_validator(mode="after")
    def _unique_anchor_ids(self) -> "AnchorsContract":
        anchor_ids = [anchor.id for anchor in self.anchors]
        duplicates = sorted({anchor_id for anchor_id in anchor_ids if anchor_ids.count(anchor_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate anchor ids: {', '.join(duplicates)}")
        return self

    def anchor_map(self) -> dict[str, AnchorDefinition]:
        return {anchor.id: anchor for anchor in self.anchors}

    @property
    def device_id(self) -> str:
        return self.profile_id

    @property
    def actions(self) -> list[str]:
        values: list[str] = []
        for anchor in self.anchors:
            for action in anchor.supported_actions:
                if action not in values:
                    values.append(action)
        return values
