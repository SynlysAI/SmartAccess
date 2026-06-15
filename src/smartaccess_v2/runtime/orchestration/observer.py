"""步骤观察和 OCR 匹配。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from smartaccess_v2.runtime.application.ports import OcrReading, VisionProvider
from smartaccess_v2.shared.contracts.anchors import AnchorDefinition, AnchorsContract


@dataclass(slots=True)
class Observation:
    """一次观察中的 OCR 读数集合。"""

    readings: list[OcrReading] = field(default_factory=list)
    min_confidence: float = 1.0


class Observer:
    """执行 OCR 观察并判断文本匹配结果。"""

    def __init__(
        self,
        vision: VisionProvider,
        *,
        confidence_threshold: float = 0.6,
    ) -> None:
        """初始化观察器。

        Args:
            vision: 视觉 provider。
            confidence_threshold: 低置信度阈值。
        """

        self._vision = vision
        self._threshold = confidence_threshold
        self._screenshot: bytes | None = None

    def configure_screenshot(self, data: bytes | None) -> None:
        """配置后续 OCR 使用的截图。

        Args:
            data: 截图 PNG 字节。
        """

        self._screenshot = data
        configure = getattr(self._vision, "configure_screenshot", None)
        if callable(configure):
            configure(data)

    def observe_anchor(
        self,
        profile: AnchorsContract | None,
        anchor_id: str | None,
    ) -> Observation:
        """读取指定锚点的观察区域。

        Args:
            profile: 当前锚点配置。
            anchor_id: 锚点 ID。

        Returns:
            OCR 观察结果。
        """

        if not anchor_id:
            return Observation()
        if profile is None:
            reading = self._vision.read_text(anchor_id)
            return Observation(readings=[reading], min_confidence=reading.confidence)
        anchor = profile.anchor_map().get(anchor_id)
        if anchor is None:
            reading = self._vision.read_text(anchor_id)
            return Observation(readings=[reading], min_confidence=reading.confidence)
        reading = self._read_anchor(anchor)
        return Observation(readings=[reading], min_confidence=reading.confidence)

    def anchor_snapshot(
        self,
        profile: AnchorsContract | None,
        anchor_id: str | None,
    ) -> bytes | None:
        """返回锚点观察区域截图。

        Args:
            profile: 当前锚点配置。
            anchor_id: 锚点 ID。

        Returns:
            PNG 截图字节；无法裁剪时返回 None。
        """

        if profile is None or not anchor_id:
            return None
        anchor = profile.anchor_map().get(anchor_id)
        if anchor is None:
            return None
        capture = getattr(self._vision, "capture_anchor_image", None)
        if not callable(capture):
            return None
        return capture(screenshot=self._screenshot, anchor=anchor)

    def matches(
        self,
        reading: OcrReading | None,
        *,
        expected_text: str | None,
        match_mode: str,
    ) -> bool | None:
        """判断 OCR 文本是否满足期望。

        Args:
            reading: OCR 读数。
            expected_text: 期望文本。
            match_mode: 匹配模式。

        Returns:
            匹配结果；无匹配要求时返回 None。
        """

        if match_mode == "none":
            return None
        if reading is None:
            return False
        text = reading.text or ""
        if match_mode == "not_empty":
            return bool(text.strip())
        if expected_text is None:
            return False
        if match_mode == "contains":
            return expected_text in text
        if match_mode == "equals":
            return expected_text == text
        if match_mode == "regex":
            return re.search(expected_text, text) is not None
        return False

    def is_low_confidence(self, observation: Observation) -> bool:
        """返回观察结果是否低置信度。"""

        return observation.min_confidence < self._threshold

    def _read_anchor(self, anchor: AnchorDefinition) -> OcrReading:
        """读取单个锚点的观察区域。"""

        if anchor.observe_region is None:
            return OcrReading(roi=anchor.id, text="", confidence=1.0, detail="none")
        return self._vision.read_roi_text(
            screenshot=self._screenshot,
            anchor=anchor,
            roi=None,
        )
