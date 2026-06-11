"""Cross-contract validation helpers for SmartAccess v2 contracts."""

from __future__ import annotations

import re

from .anchors import AnchorsContract
from .workflow import WorkflowContract


def validate_workflow_against_anchors(
    workflow: WorkflowContract,
    anchors: AnchorsContract | None,
) -> list[str]:
    """Return structural issues for a workflow relative to an anchor profile."""

    issues: list[str] = []
    if not workflow.steps:
        issues.append("workflow.steps must not be empty")
    if anchors is None:
        issues.append(f"anchor profile not found: {workflow.metadata.anchor_profile}")
        return issues
    if workflow.metadata.anchor_profile != anchors.profile_id:
        issues.append(
            "workflow.metadata.anchor_profile must match anchors.profile_id"
        )

    anchor_map = anchors.anchor_map()
    for step in workflow.steps:
        anchor = anchor_map.get(step.anchor_id)
        if anchor is None:
            issues.append(f"step {step.id}: unknown anchor_id '{step.anchor_id}'")
            continue
        if step.action not in anchor.supported_actions:
            issues.append(
                f"step {step.id}: action '{step.action}' not supported by anchor '{step.anchor_id}'"
            )
        needs_observe_region = step.match_mode != "none"
        if needs_observe_region and anchor.observe_region is None:
            issues.append(
                f"step {step.id}: anchor '{step.anchor_id}' requires observe_region for OCR matching"
            )
        if step.match_mode in {"contains", "equals", "regex"} and not (step.expected_text or "").strip():
            issues.append(
                f"step {step.id}: expected_text is required when match_mode is '{step.match_mode}'"
            )
        if step.match_mode == "regex" and step.expected_text:
            try:
                re.compile(step.expected_text)
            except re.error as exc:
                issues.append(f"step {step.id}: invalid regex '{step.expected_text}': {exc}")
    return issues
