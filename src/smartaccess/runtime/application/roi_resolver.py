"""Resolve calibrated ROI coordinates against the current window size."""

from __future__ import annotations

from smartaccess.shared.contracts.anchors import AnchorDefinition, PixelRegion, WindowSignature


def resolve_anchor_roi(
    anchor: AnchorDefinition,
    signature: WindowSignature | None,
    *,
    current_width: int | None = None,
    current_height: int | None = None,
) -> PixelRegion | None:
    """Return the best absolute ROI for the current window dimensions."""

    if (
        anchor.action_region.normalized is not None
        and current_width
        and current_height
        and current_width > 0
        and current_height > 0
    ):
        normalized = anchor.action_region.normalized
        return PixelRegion(
            x=normalized.x * current_width,
            y=normalized.y * current_height,
            width=normalized.width * current_width,
            height=normalized.height * current_height,
        )
    if anchor.action_region.pixel is not None:
        return anchor.action_region.pixel
    if (
        anchor.action_region.normalized is not None
        and signature is not None
        and signature.capture_width
        and signature.capture_height
    ):
        normalized = anchor.action_region.normalized
        return PixelRegion(
            x=normalized.x * signature.capture_width,
            y=normalized.y * signature.capture_height,
            width=normalized.width * signature.capture_width,
            height=normalized.height * signature.capture_height,
        )
    return None


def aspect_ratio_drift(signature: WindowSignature | None, *, current_width: int, current_height: int) -> float:
    """Return relative aspect-ratio drift from calibration capture size."""

    if not signature or not signature.capture_width or not signature.capture_height or current_height <= 0:
        return 0.0
    base = signature.capture_width / signature.capture_height
    current = current_width / current_height
    if base == 0:
        return 0.0
    return abs(current - base) / base
