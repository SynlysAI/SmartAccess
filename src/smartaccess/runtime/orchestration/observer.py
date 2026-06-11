"""Observer: collect screenshots and produce structured observations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from smartaccess.runtime.application.ports import OcrReading, VisionProvider
from smartaccess.shared.contracts.anchors import AnchorDefinition, AnchorsContract


@dataclass(slots=True)
class Observation:
    """A batch of ROI readings with the weakest confidence highlighted."""

    readings: list[OcrReading] = field(default_factory=list)
    min_confidence: float = 1.0


class Observer:
    """Produces observations and judges their confidence."""

    def __init__(self, vision: VisionProvider, *, confidence_threshold: float = 0.6) -> None:
        self._vision = vision
        self._threshold = confidence_threshold

    def configure_screenshot(self, data: bytes | None) -> None:
        configure = getattr(self._vision, "configure_screenshot", None)
        if callable(configure):
            configure(data)

    def observe_anchor(
        self,
        profile: AnchorsContract | None,
        anchor_id: str,
    ) -> Observation:
        if profile is None:
            reading = self._vision.read_text(anchor_id)
            return Observation(readings=[reading], min_confidence=reading.confidence)
        anchor = profile.anchor_map().get(anchor_id)
        if anchor is None:
            reading = self._vision.read_text(anchor_id)
            return Observation(readings=[reading], min_confidence=reading.confidence)
        reading = self._read_anchor(anchor)
        return Observation(readings=[reading], min_confidence=reading.confidence)

    def _read_anchor(self, anchor: AnchorDefinition) -> OcrReading:
        if anchor.observe_region is None:
            return OcrReading(roi=anchor.id, text="", confidence=1.0, detail="none")
        return self._vision.read_roi_text(
            screenshot=None,
            anchor=anchor,
            roi=anchor.observe_region.pixel,
        )

    def matches(self, reading: OcrReading, *, expected_text: str | None, match_mode: str) -> bool | None:
        if match_mode == "none":
            return None
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
        return observation.min_confidence < self._threshold
