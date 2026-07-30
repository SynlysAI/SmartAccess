"""anchors.yaml 的契约模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, FlexibleContractModel, JsonMap, NonEmptyStr

WORKFLOW_ACTIONS: tuple[str, ...] = (
    "click",
    "type",
    "hotkey",
    "press_enter",
    "ocr",
    "wait",
)


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
    capture_origin_x: int | None = None
    capture_origin_y: int | None = None
    capture_mode: Literal["window", "screen_canvas"] = "window"
    capture_screen_origin_x: int | None = None
    capture_screen_origin_y: int | None = None
    capture_windows: list[JsonMap] = Field(default_factory=list)

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


class AnchorPrecheck(FlexibleContractModel):
    """锚点执行前的视觉校验配置。"""

    mode: Literal["image", "text", "image_text"]
    region: AnchorRegion
    image_threshold: float = Field(default=0.8, ge=0, le=1)
    ignore_case: bool = Field(default=True, exclude=True)
    normalize_text: bool = Field(default=True, exclude=True)

    @model_validator(mode="after")
    def _fix_text_normalization(self) -> "AnchorPrecheck":
        """固定文字校验使用忽略大小写和 NFKC 归一化。"""

        self.ignore_case = True
        self.normalize_text = True
        return self


class ExceptionRule(FlexibleContractModel):
    """设备级异常弹窗识别规则。"""

    id: NonEmptyStr
    view_id: NonEmptyStr
    anchor_id: NonEmptyStr
    expected_text: str | list[str] | None = None
    match_mode: Literal["contains", "equals", "regex", "not_empty"] = "contains"
    ignore_case: bool = False
    normalize_text: bool = False
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    blocking: bool = True
    message: str | None = None


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


class AnchorDefinition(FlexibleContractModel):
    """目标软件界面上的一个可操作或可观察锚点。"""

    id: NonEmptyStr
    action_region: AnchorRegion
    precheck: AnchorPrecheck | None = None
    notes: str | None = None


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
    exception_rules: list[ExceptionRule] = Field(default_factory=list)
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
        """返回工作流当前支持的动作列表。"""

        return list(WORKFLOW_ACTIONS)
