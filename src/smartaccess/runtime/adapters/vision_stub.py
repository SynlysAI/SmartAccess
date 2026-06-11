"""Deterministic vision/OCR stub.

Stands in for OpenCV/PaddleOCR. Readings are derived from the ROI name so the
monitoring page shows believable values (voltage, run status). By default the
first reading of each ROI returns low confidence so the recovery path is
exercised once; the resample then returns high confidence. Set
``low_confidence_first=False`` for a clean run.
"""

from __future__ import annotations

from smartaccess.runtime.application.ports import OcrReading
from smartaccess.shared.contracts.anchors import AnchorDefinition, PixelRegion


class StubVisionProvider:
    """Deterministic OCR/presence provider for local runs and tests."""

    def __init__(self, *, low_confidence_first: bool = True) -> None:
        self._low_confidence_first = low_confidence_first
        self._seen: dict[str, int] = {}

    def read_text(self, roi: str) -> OcrReading:
        count = self._seen.get(roi, 0)
        self._seen[roi] = count + 1
        confidence = 0.95
        if self._low_confidence_first and count == 0:
            confidence = 0.45
        return OcrReading(roi=roi, text=self._value_for(roi), confidence=confidence)

    def read_roi_text(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: PixelRegion | None = None,
    ) -> OcrReading:
        reading = self.read_text(anchor.id)
        detail = "stub OCR"
        if roi is not None:
            detail = f"stub OCR roi=({roi.x:.0f},{roi.y:.0f},{roi.width:.0f},{roi.height:.0f})"
        return OcrReading(
            roi=anchor.id,
            text=reading.text,
            confidence=reading.confidence,
            detail=detail,
        )

    def detect_presence(self, roi: str) -> bool:
        return True

    def match_template(self, roi: str) -> OcrReading:
        return OcrReading(roi=roi, text="matched", confidence=0.92, detail="stub template match")

    def sample_color(self, roi: str) -> OcrReading:
        return OcrReading(roi=roi, text="green", confidence=0.9, detail="stub color sample")

    @staticmethod
    def _value_for(roi: str) -> str:
        lowered = roi.lower()
        if "voltage" in lowered:
            return "4.20"
        if "status" in lowered:
            return "Running"
        if "temp" in lowered:
            return "25.0"
        return "OK"
