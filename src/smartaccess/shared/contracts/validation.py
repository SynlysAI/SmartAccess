"""SmartAccess 跨契约校验工具。"""

from __future__ import annotations

import re

from .anchors import AnchorsContract
from .workflow import EXECUTABLE_WORKFLOW_ACTIONS, WorkflowContract


def validate_workflow_against_anchors(
    workflow: WorkflowContract,
    anchors: AnchorsContract | None,
) -> list[str]:
    """校验工作流是否匹配锚点配置。

    Args:
        workflow: 工作流契约。
        anchors: 锚点契约；未找到时传 None。

    Returns:
        校验问题列表；为空表示通过。
    """

    issues: list[str] = []
    if not workflow.steps:
        issues.append("workflow.steps must not be empty")
    if anchors is None:
        issues.append(f"anchor profile not found: {workflow.metadata.anchor_profile}")
        return issues
    if workflow.metadata.anchor_profile != anchors.profile_id:
        issues.append("workflow.metadata.anchor_profile must match anchors.profile_id")

    anchor_map = anchors.anchor_map()
    for step in workflow.steps:
        if step.action == "wait":
            _validate_wait_step(step.id, step.wait_seconds, issues)
            continue
        if step.action not in EXECUTABLE_WORKFLOW_ACTIONS:
            issues.append(f"step {step.id}: unsupported action '{step.action}'")
            continue
        if not step.anchor_id:
            issues.append(f"step {step.id}: anchor_id is required")
            continue
        anchor = anchor_map.get(step.anchor_id)
        if anchor is None:
            issues.append(f"step {step.id}: unknown anchor_id '{step.anchor_id}'")
            continue
        if step.action not in anchor.supported_actions:
            issues.append(
                f"step {step.id}: action '{step.action}' not supported by "
                f"anchor '{step.anchor_id}'"
            )
        needs_observe_region = step.match_mode != "none"
        if needs_observe_region and anchor.observe_region is None:
            issues.append(
                f"step {step.id}: anchor '{step.anchor_id}' requires "
                "observe_region for OCR matching"
            )
        _validate_text_expectation(step.id, step.match_mode, step.expected_text, issues)
    return issues


def _validate_wait_step(
    step_id: str,
    wait_seconds: float | None,
    issues: list[str],
) -> None:
    """校验固定等待步骤。"""

    if wait_seconds is None or wait_seconds < 0:
        issues.append(f"step {step_id}: wait_seconds must be greater than or equal to 0")


def _validate_text_expectation(
    step_id: str,
    match_mode: str,
    expected_text: str | None,
    issues: list[str],
) -> None:
    """校验 OCR 文本匹配字段。"""

    if match_mode in {"contains", "equals", "regex"} and not (
        expected_text or ""
    ).strip():
        issues.append(
            f"step {step_id}: expected_text is required when "
            f"match_mode is '{match_mode}'"
        )
    if match_mode == "regex" and expected_text:
        try:
            re.compile(expected_text)
        except re.error as exc:
            issues.append(f"step {step_id}: invalid regex '{expected_text}': {exc}")
