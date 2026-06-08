"""Instrument profile domain types (SPEC §4, §5.3)."""

from __future__ import annotations

from enum import StrEnum


class InstrumentStatus(StrEnum):
    """Lifecycle of a calibrated instrument profile."""

    DRAFT = "Draft"
    CALIBRATED = "Calibrated"
    ACTIVE = "Active"
    DEPRECATED = "Deprecated"


class RoiKind(StrEnum):
    """Anchors split into action targets and observation regions (SPEC §5.3)."""

    ACTION_TARGET = "action_target"
    OBSERVATION = "observation"
