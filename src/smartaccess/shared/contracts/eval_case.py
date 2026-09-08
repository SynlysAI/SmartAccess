"""Evaluation case contract models."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class EvalScenario(FlexibleContractModel):
    """Stable identifier and label for an evaluation case."""

    id: NonEmptyStr
    title: str | None = None


class EvalCaseContract(ContractModel):
    """Top-level evaluation harness case contract."""

    scenario: EvalScenario
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_events: list[Any] = Field(default_factory=list)
    pass_criteria: list[NonEmptyStr] = Field(default_factory=list)
    fixtures: dict[str, Any] = Field(default_factory=dict)
