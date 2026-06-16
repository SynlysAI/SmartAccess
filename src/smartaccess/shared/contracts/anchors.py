"""anchors.yaml 的契约模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, FlexibleContractModel, JsonMap, NonEmptyStr

SIMPLIFIED_ACTIONS: tuple[str, ...] = (
    "click",
    "type",
    "hotkey",
    "press_enter",
)
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
    """锚点截图的参考尺寸。"""

    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)


class WindowSignature(FlexibleContractModel):
    """用于定位目标软件窗口的线索。"""

    title_contains: str | None = None
    process_name: str | None = None
    screenshot_size: ScreenshotSize | None = None
    match_mode: Literal["equals", "contains"] = "equals"

    @property
    def capture_width(self) -> int | None:
        """返回截图宽度。"""

        return self.screenshot_size.width if self.screenshot_size else None

    @property
    def capture_height(self) -> int | None:
        """返回截图高度。"""

        return self.screenshot_size.height if self.screenshot_size else None


class PixelRegion(FlexibleContractModel):
    """截图像素坐标区域。"""

    x: float = Field(default=0, ge=0)
    y: float = Field(default=0, ge=0)
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)


class NormalizedRegion(FlexibleContractModel):
    """相对截图尺寸归一化后的区域。"""

    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=0, ge=0, le=1)
    height: float = Field(default=0, ge=0, le=1)


class AnchorRegion(FlexibleContractModel):
    """同时保存像素和归一化坐标的锚点区域。"""

    pixel: PixelRegion
    normalized: NormalizedRegion


class VisionConfig(FlexibleContractModel):
    """视觉识别配置。"""

    template_asset_path: str | None = None
    template_threshold: float = Field(default=0.8, ge=0, le=1)
    color_reference_hex: str | None = None
    color_tolerance: float = Field(default=0.1, ge=0, le=1)
    presence_threshold: float = Field(default=0.05, ge=0, le=1)


class SafetyField(FlexibleContractModel):
    """绑定到字段或步骤的安全确认规则。"""

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
    """运行时安全限制。"""

    max_voltage: float | None = None
    min_voltage: float | None = None
    requires_manual_confirm_for: list[str] = Field(default_factory=list)
    fields: list[SafetyField] = Field(default_factory=list)


class AnchorActionBinding(FlexibleContractModel):
    """锚点支持的动作绑定。"""

    action: NonEmptyStr
    requires_confirmation: bool = False
    default_value: str | None = None
    hotkey: str | None = None
    metadata: JsonMap = Field(default_factory=dict)


class AnchorDefinition(FlexibleContractModel):
    """目标软件界面上的一个动作或观察锚点。"""

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
        """兼容旧版 roi/normalized_roi 结构。"""

        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "action_region" not in data:
            data["action_region"] = {
                "pixel": data.get("roi") or {},
                "normalized": data.get("normalized_roi") or {},
            }
        if "observe_region" not in data:
            vision_mode = data.get("vision_mode") or "none"
            legacy_type = data.get("type")
            if (
                vision_mode == "ocr"
                or legacy_type in {"observation", "readout", "status", "region", "roi"}
            ):
                data["observe_region"] = {
                    "pixel": data.get("observe_roi") or data.get("roi") or {},
                    "normalized": (
                        data.get("observe_normalized_roi")
                        or data.get("normalized_roi")
                        or {}
                    ),
                }
        if "label" not in data and data.get("id"):
            data["label"] = data["id"]
        return data

    @model_validator(mode="after")
    def _normalize_compat_fields(self) -> "AnchorDefinition":
        """标准化兼容字段和动作绑定。"""

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
            action
            for action in dict.fromkeys(self.supported_actions)
            if action in SIMPLIFIED_ACTIONS
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


class AnchorView(FlexibleContractModel):
    """同一被控应用中的一个可校准窗口或页面视图。"""

    view_id: NonEmptyStr
    window_signature: WindowSignature | None = None
    screenshot_size: ScreenshotSize | None = None
    anchors: list[AnchorDefinition] = Field(default_factory=list)
    capture_asset_path: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _sync_screenshot_size(self) -> "AnchorView":
        """让视图级 screenshot_size 与 window_signature 保持兼容。"""

        if self.window_signature is None:
            self.window_signature = WindowSignature()
        if self.screenshot_size is None:
            self.screenshot_size = self.window_signature.screenshot_size
        elif self.window_signature.screenshot_size is None:
            self.window_signature.screenshot_size = self.screenshot_size
        return self


class AnchorsContract(ContractModel):
    """锚点配置顶层契约。"""

    profile_id: NonEmptyStr
    window_signature: WindowSignature
    anchors: list[AnchorDefinition] = Field(default_factory=list)
    views: list[AnchorView] = Field(default_factory=list)
    supported_os: list[NonEmptyStr] = Field(default_factory=list, exclude=True)
    safety_limits: SafetyLimits = Field(default_factory=SafetyLimits, exclude=True)

    @model_validator(mode="after")
    def _unique_anchor_ids(self) -> "AnchorsContract":
        """检查锚点 ID 不重复。"""

        original_anchors = list(self.anchors)
        if not self.views:
            self.views = [
                AnchorView(
                    view_id="main",
                    window_signature=self.window_signature,
                    screenshot_size=self.window_signature.screenshot_size,
                    anchors=list(self.anchors),
                    capture_asset_path="capture.png",
                )
            ]
        if not original_anchors:
            self.anchors = [anchor for view in self.views for anchor in view.anchors]
        anchor_ids = [anchor.id for anchor in self.anchors]
        duplicates = sorted(
            {anchor_id for anchor_id in anchor_ids if anchor_ids.count(anchor_id) > 1}
        )
        if duplicates:
            raise ValueError(f"duplicate anchor ids: {', '.join(duplicates)}")
        view_ids = [view.view_id for view in self.views]
        duplicate_views = sorted(
            {view_id for view_id in view_ids if view_ids.count(view_id) > 1}
        )
        if duplicate_views:
            raise ValueError(f"duplicate view ids: {', '.join(duplicate_views)}")
        return self

    def anchor_map(self) -> dict[str, AnchorDefinition]:
        """返回按锚点 ID 索引的锚点字典。

        Returns:
            锚点 ID 到锚点定义的映射。
        """

        return {anchor.id: anchor for anchor in self.anchors}

    def view_map(self) -> dict[str, AnchorView]:
        """返回按视图 ID 索引的视图字典。"""

        return {view.view_id: view for view in self.views}

    def anchors_for_view(self, view_id: str | None) -> list[AnchorDefinition]:
        """返回指定视图中的锚点；未指定时使用 main。"""

        view = self.view_map().get(view_id or "main")
        return list(view.anchors) if view is not None else []

    def anchor_for_view(
        self,
        view_id: str | None,
        anchor_id: str | None,
    ) -> AnchorDefinition | None:
        """返回指定视图中的锚点。"""

        if not anchor_id:
            return None
        return next(
            (anchor for anchor in self.anchors_for_view(view_id) if anchor.id == anchor_id),
            None,
        )

    @property
    def device_id(self) -> str:
        """返回兼容旧界面的设备 ID。"""

        return self.profile_id

    @property
    def actions(self) -> list[str]:
        """返回当前锚点配置支持的动作列表。"""

        values: list[str] = []
        for anchor in self.anchors:
            for action in anchor.supported_actions:
                if action not in values:
                    values.append(action)
        return values
