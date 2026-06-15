"""按当前窗口尺寸解析校准 ROI 坐标。"""

from __future__ import annotations

from smartaccess.shared.contracts.anchors import (
    AnchorDefinition,
    PixelRegion,
    WindowSignature,
)


def resolve_anchor_roi(
    anchor: AnchorDefinition,
    signature: WindowSignature | None,
    *,
    current_width: int | None = None,
    current_height: int | None = None,
) -> PixelRegion | None:
    """返回当前窗口尺寸下最合适的绝对 ROI。

    Args:
        anchor: 锚点定义。
        signature: 锚点配置中的窗口签名。
        current_width: 当前窗口宽度。
        current_height: 当前窗口高度。

    Returns:
        像素坐标 ROI；无法解析时返回 None。
    """

    normalized = anchor.action_region.normalized
    if current_width and current_height and current_width > 0 and current_height > 0:
        return PixelRegion(
            x=normalized.x * current_width,
            y=normalized.y * current_height,
            width=normalized.width * current_width,
            height=normalized.height * current_height,
        )
    if anchor.action_region.pixel is not None:
        return anchor.action_region.pixel
    if signature and signature.capture_width and signature.capture_height:
        return PixelRegion(
            x=normalized.x * signature.capture_width,
            y=normalized.y * signature.capture_height,
            width=normalized.width * signature.capture_width,
            height=normalized.height * signature.capture_height,
        )
    return None


def aspect_ratio_drift(
    signature: WindowSignature | None,
    *,
    current_width: int,
    current_height: int,
) -> float:
    """计算当前窗口相对校准截图的宽高比漂移。

    Args:
        signature: 锚点配置中的窗口签名。
        current_width: 当前窗口宽度。
        current_height: 当前窗口高度。

    Returns:
        相对漂移比例。
    """

    if (
        not signature
        or not signature.capture_width
        or not signature.capture_height
        or current_height <= 0
    ):
        return 0.0
    base = signature.capture_width / signature.capture_height
    current = current_width / current_height
    if base == 0:
        return 0.0
    return abs(current - base) / base
