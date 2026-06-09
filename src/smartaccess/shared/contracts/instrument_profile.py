"""Pydantic models for `instrument_profile.yaml`."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, JsonMap, NonEmptyStr


class WindowSignature(FlexibleContractModel):
    """Visual and windowing hints used to find an instrument UI."""

    title_contains: str | None = None
    min_width: int | None = Field(default=None, ge=0)
    min_height: int | None = Field(default=None, ge=0)
    capture_width: int | None = Field(default=None, ge=0)
    capture_height: int | None = Field(default=None, ge=0)


class RoiRect(FlexibleContractModel):
    """ROI rectangle in screenshot pixel coordinates."""

    x: float = Field(default=0, ge=0)
    y: float = Field(default=0, ge=0)
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)


class NormalizedRoiRect(FlexibleContractModel):
    """ROI rectangle normalized to the screenshot size, used after window resize."""

    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=0, ge=0, le=1)
    height: float = Field(default=0, ge=0, le=1)


class VisionConfig(FlexibleContractModel):
    """Calibrated visual references for template matching, color detection, and presence checks."""

    template_asset_path: str | None = None
    template_threshold: float = Field(default=0.8, ge=0, le=1)
    color_reference_hex: str | None = None
    color_tolerance: float = Field(default=0.1, ge=0, le=1)
    presence_threshold: float = Field(default=0.05, ge=0, le=1)


class ActionBinding(FlexibleContractModel):
    """An action primitive bound to a concrete anchor."""

    action: NonEmptyStr
    requires_confirmation: bool = False
    default_value: str | None = None
    hotkey: str | None = None
    metadata: JsonMap = Field(default_factory=dict)


class AnchorDefinition(FlexibleContractModel):
    """Action target or observation region within the instrument UI."""

    id: NonEmptyStr
    type: NonEmptyStr
    locator_hint: str | None = None
    roi: RoiRect | None = None
    normalized_roi: NormalizedRoiRect | None = None
    action_bindings: list[ActionBinding] = Field(default_factory=list)
    vision_mode: Literal["ocr", "template", "presence", "color", "none"] = "none"
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    vision_config: VisionConfig | None = None


class SafetyField(FlexibleContractModel):
    """Generic safety or confirmation rule bound to a field or workflow step."""

    field_id: NonEmptyStr
    label: NonEmptyStr
    value_type: Literal["string", "number", "bool", "choice"] = "string"
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    risk_level: Literal["low", "medium", "high"] = "medium"
    applies_to_steps: list[str] = Field(default_factory=list)


class SafetyLimits(FlexibleContractModel):
    """Safety limits bound to actions or runtime parameters.

    The voltage fields are kept for backward compatibility with existing examples,
    while new profiles should prefer generic ``fields`` entries.
    """

    max_voltage: float | None = None
    min_voltage: float | None = None
    requires_manual_confirm_for: list[str] = Field(default_factory=list)
    fields: list[SafetyField] = Field(default_factory=list)


class InstrumentProfileContract(ContractModel):
    """Top-level contract for calibrated instrument profiles."""

    device_id: NonEmptyStr
    supported_os: list[NonEmptyStr] = Field(default_factory=list)
    window_signature: WindowSignature
    anchors: list[AnchorDefinition] = Field(default_factory=list)
    actions: list[NonEmptyStr] = Field(default_factory=list)
    safety_limits: SafetyLimits
