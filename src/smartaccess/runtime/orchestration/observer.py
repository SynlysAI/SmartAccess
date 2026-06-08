"""Observer: collect screenshots and produce structured observations.

Wraps the :class:`VisionProvider` port. Each observation carries source ROI,
confidence, and timestamp; low-confidence results are flagged so the
orchestrator can resample, wait, or escalate rather than driving the next step
(SPEC §5.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from smartaccess.runtime.application.ports import OcrReading, VisionProvider


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

    def is_low_confidence(self, observation: Observation) -> bool:
        return observation.min_confidence < self._threshold
