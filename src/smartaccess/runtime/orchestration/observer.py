"""Observer: collect screenshots and produce structured observations.

Wraps the :class:`VisionProvider` port. Each observation carries source ROI,
confidence, and timestamp; low-confidence results are flagged so the
orchestrator can resample, wait, or escalate rather than driving the next step
(SPEC §5.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from smartaccess.runtime.application.ports import OcrReading, VisionProvider
from smartaccess.shared.contracts.instrument_profile import AnchorDefinition, InstrumentProfileContract


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

    def observe(self, rois: list[str]) -> Observation:
        readings = [self._vision.read_text(roi) for roi in rois]
        min_conf = min((r.confidence for r in readings), default=1.0)
        return Observation(readings=readings, min_confidence=min_conf)

    def observe_profile(self, profile: InstrumentProfileContract | None, sources: list[str]) -> Observation:
        anchors = {anchor.id: anchor for anchor in profile.anchors} if profile else {}
        readings = [self.observe_anchor(anchors.get(source), source) for source in sources]
        min_conf = min((r.confidence for r in readings), default=1.0)
        return Observation(readings=readings, min_confidence=min_conf)

    def observe_anchor(self, anchor: AnchorDefinition | None, source: str) -> OcrReading:
        if anchor is None:
            return self._vision.read_text(source)
        mode = anchor.vision_mode
        if mode == "presence":
            present = self._vision.detect_presence(anchor.id)
            return OcrReading(
                roi=anchor.id,
                text="present" if present else "missing",
                confidence=1.0 if present else 0.0,
                detail="presence",
            )
        if mode == "template":
            return self._vision.match_template(anchor.id)
        if mode == "color":
            return self._vision.sample_color(anchor.id)
        if mode == "none":
            return OcrReading(roi=anchor.id, text="not_observed", confidence=1.0, detail="none")
        return self._vision.read_roi_text(screenshot=None, anchor=anchor, roi=anchor.roi)

    def condition_passed(self, observation: Observation, condition: dict | None) -> bool:
        if not condition:
            return True
        expected = condition.get("expected")
        operator = str(condition.get("operator") or "exists")
        reading = observation.readings[0] if observation.readings else None
        if reading is None:
            return False
        if operator == "exists":
            return reading.confidence > 0 and reading.text not in {"missing", "not_observed"}
        if operator == "equals":
            return str(reading.text) == str(expected)
        if operator == "contains":
            return str(expected or "") in str(reading.text)
        if operator == "not_empty":
            return bool(str(reading.text).strip())
        return True

    def is_low_confidence(self, observation: Observation) -> bool:
        return observation.min_confidence < self._threshold
