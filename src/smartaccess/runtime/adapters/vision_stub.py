"""确定性的视觉/OCR Stub。"""

from __future__ import annotations

from smartaccess.runtime.application.ports import OcrReading, VisualCheckResult
from smartaccess.shared.contracts.anchors import AnchorDefinition, PixelRegion


class StubVisionProvider:
    """用于本地运行和服务验证的 OCR 提供者。"""

    def __init__(self, *, low_confidence_first: bool = True) -> None:
        """初始化 Stub OCR。

        Args:
            low_confidence_first: 每个 ROI 首次读取是否返回低置信度。
        """

        self._low_confidence_first = low_confidence_first
        self._seen: dict[str, int] = {}

    def read_text(self, roi: str) -> OcrReading:
        """读取指定 ROI 的模拟文本。

        Args:
            roi: ROI 名称。

        Returns:
            OCR 读取结果。
        """

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
        """读取锚点观察区域的模拟 OCR 文本。"""

        reading = self.read_text(anchor.id)
        detail = "stub OCR"
        if roi is not None:
            detail = (
                f"stub OCR roi=({roi.x:.0f},{roi.y:.0f},"
                f"{roi.width:.0f},{roi.height:.0f})"
            )
        return OcrReading(
            roi=anchor.id,
            text=reading.text,
            confidence=reading.confidence,
            detail=detail,
        )

    @staticmethod
    def detect_presence(roi: str) -> bool:
        """检测模拟目标是否存在。"""

        return bool(roi)

    @staticmethod
    def match_template(roi: str) -> OcrReading:
        """返回模拟模板匹配结果。"""

        return OcrReading(
            roi=roi,
            text="matched",
            confidence=0.92,
            detail="stub template match",
        )

    @staticmethod
    def sample_color(roi: str) -> OcrReading:
        """返回模拟颜色采样结果。"""

        return OcrReading(
            roi=roi,
            text="green",
            confidence=0.9,
            detail="stub color sample",
        )

    @staticmethod
    def validate_anchor(
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        profile_id: str,
        view_id: str,
    ) -> VisualCheckResult:
        """返回模拟锚点执行前校验结果。"""

        return VisualCheckResult(
            passed=True,
            image_score=0.99 if anchor.precheck is not None else None,
            detail=f"stub precheck profile={profile_id} view={view_id}",
        )

    @staticmethod
    def _value_for(roi: str) -> str:
        """按 ROI 名称返回可预测文本。"""

        lowered = roi.lower()
        if "voltage" in lowered:
            return "4.20"
        if "status" in lowered or "start" in lowered:
            return "Running"
        if "temp" in lowered:
            return "25.0"
        return "OK"
