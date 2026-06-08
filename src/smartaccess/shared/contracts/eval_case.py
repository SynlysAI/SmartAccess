"""Pydantic models for `eval_case.yaml` and harness eval cases."""

from __future__ import annotations

from typing import Any

from pydantic import Field, RootModel

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class EvalScenario(FlexibleContractModel):
    """Scenario identity and title."""

    id: NonEmptyStr
    title: NonEmptyStr


class EvalInputs(FlexibleContractModel):
    """Scenario inputs, intentionally extensible across eval families."""

    required_docs: list[str] = Field(default_factory=list)
    fixtures: list[str] = Field(default_factory=list)


class ExpectedEventEntry(RootModel[str | dict[str, Any]]):
    """Expected event can be a symbolic string or a structured mapping."""


class EvalFixtures(FlexibleContractModel):
    """Auxiliary files, skills, agents, or services used by the eval."""


class EvalCaseContract(ContractModel):
    """Top-level eval case contract."""

    scenario: EvalScenario
    inputs: EvalInputs = Field(default_factory=EvalInputs)
    expected_events: list[ExpectedEventEntry] = Field(default_factory=list)
    pass_criteria: list[NonEmptyStr] = Field(default_factory=list)
    fixtures: EvalFixtures = Field(default_factory=EvalFixtures)
