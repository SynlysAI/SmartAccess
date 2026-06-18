from __future__ import annotations

from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.validation import validate_workflow_against_anchors
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowMetadata, WorkflowStep


def _anchor(anchor_id: str) -> dict:
    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 10, "y": 20, "width": 80, "height": 30},
            "normalized": {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.1},
        },
        "supported_actions": ["click"],
    }


def _ocr_anchor(anchor_id: str) -> dict:
    anchor = _anchor(anchor_id)
    anchor["observe_region"] = {
        "pixel": {"x": 100, "y": 120, "width": 160, "height": 60},
        "normalized": {"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.1},
    }
    return anchor


def test_legacy_anchor_profile_is_exposed_as_main_view() -> None:
    profile = AnchorsContract(
        profile_id="device_1",
        window_signature={
            "title_contains": "Main Window",
            "screenshot_size": {"width": 800, "height": 600},
        },
        anchors=[_anchor("start")],
    )

    assert profile.view_map()["main"].view_id == "main"
    assert profile.view_map()["main"].window_signature.title_contains == "Main Window"
    assert profile.view_map()["main"].anchors[0].id == "start"
    assert profile.anchor_map()["start"].id == "start"


def test_multiview_anchor_profile_indexes_views_and_anchors() -> None:
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "device_1",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {
                    "view_id": "main",
                    "window_signature": {"title_contains": "Main Window"},
                    "screenshot_size": {"width": 800, "height": 600},
                    "anchors": [_anchor("start")],
                },
                {
                    "view_id": "dialog_confirm",
                    "window_signature": {"title_contains": "Confirm"},
                    "screenshot_size": {"width": 360, "height": 220},
                    "anchors": [_anchor("ok_button")],
                },
            ],
        }
    )

    assert sorted(profile.view_map()) == ["dialog_confirm", "main"]
    assert profile.anchor_for_view("dialog_confirm", "ok_button").id == "ok_button"
    assert profile.anchor_for_view("main", "ok_button") is None
    assert profile.anchor_map()["ok_button"].id == "ok_button"


def test_workflow_step_defaults_to_main_view_and_serializes_view_id() -> None:
    workflow = WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id="wf_multiview",
            author="test",
            anchor_profile="device_1",
            lifecycle_state="Draft",
        ),
        steps=[
            WorkflowStep(id="start", action="click", anchor_id="start"),
            WorkflowStep(
                id="confirm",
                action="click",
                anchor_id="ok_button",
                view_id="dialog_confirm",
            ),
        ],
    )

    assert workflow.steps[0].view_id == "main"
    assert workflow.steps[1].view_id == "dialog_confirm"
    payload = workflow.model_dump(mode="json", exclude_none=True)
    assert payload["steps"][0]["view_id"] == "main"
    assert payload["steps"][1]["view_id"] == "dialog_confirm"


def test_workflow_step_normalizes_enhanced_ocr_condition() -> None:
    step = WorkflowStep.model_validate(
        {
            "id": "check_status",
            "action": "click",
            "anchor_id": "start",
            "condition": {
                "operator": "contains",
                "candidates": ["Running", "Complete"],
                "ignore_case": True,
                "normalize_text": True,
                "min_confidence": 0.8,
                "timeout": 3,
            },
        }
    )

    assert step.expected_text == ["Running", "Complete"]
    assert step.expected_candidates == ["Running", "Complete"]
    assert step.ignore_case is True
    assert step.normalize_text is True
    assert step.min_confidence == 0.8
    assert step.timeout_seconds == 3


def test_workflow_step_accepts_null_expected_candidates_from_ui() -> None:
    step = WorkflowStep.model_validate(
        {
            "id": "click_start",
            "action": "click",
            "anchor_id": "start",
            "match_mode": "none",
            "expected_candidates": None,
        }
    )

    assert step.expected_candidates == []


def test_workflow_step_normalizes_legacy_exact_match_mode() -> None:
    step = WorkflowStep.model_validate(
        {
            "id": "wait_for_status",
            "action": "wait",
            "anchor_id": "status",
            "match_mode": "exact",
            "expected_text": "Running",
            "timeout_seconds": 5,
        }
    )

    assert step.match_mode == "equals"


def test_workflow_contract_normalizes_legacy_exact_condition() -> None:
    workflow = WorkflowContract.model_validate(
        {
            "metadata": {
                "workflow_id": "wf_legacy_exact",
                "anchor_profile": "device_1",
                "author": "test",
                "lifecycle_state": "Draft",
            },
            "steps": [
                {
                    "id": "wait_running",
                    "action": "wait",
                    "anchor_id": "status",
                    "condition": {
                        "operator": "exact",
                        "expected": "Running",
                        "timeout_seconds": 5,
                    },
                }
            ],
        }
    )

    assert workflow.steps[0].match_mode == "equals"


def test_workflow_validation_rejects_anchor_from_different_view() -> None:
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "device_1",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {"view_id": "main", "anchors": [_anchor("main_box")]},
                {"view_id": "view_1", "anchors": [_anchor("dialog_button")]},
            ],
        }
    )
    workflow = WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id="wf_multiview",
            author="test",
            anchor_profile="device_1",
            lifecycle_state="Draft",
        ),
        steps=[
            WorkflowStep(
                id="wrong_view",
                action="click",
                view_id="main",
                anchor_id="dialog_button",
            )
        ],
    )

    issues = validate_workflow_against_anchors(workflow, profile)

    assert "step wrong_view: anchor_id 'dialog_button' is not in view 'main'" in issues


def test_wait_step_preserves_view_anchor_and_ocr_condition() -> None:
    step = WorkflowStep.model_validate(
        {
            "id": "wait_for_reset_done",
            "action": "wait",
            "view_id": "dialog_reset_done",
            "anchor_id": "reset_done_text",
            "expected_text": "复位结束",
            "match_mode": "contains",
            "timeout_seconds": 30,
            "wait_seconds": 1.5,
            "requires_confirmation": True,
        }
    )

    assert step.view_id == "dialog_reset_done"
    assert step.anchor_id == "reset_done_text"
    assert step.expected_text == "复位结束"
    assert step.match_mode == "contains"
    assert step.timeout_seconds == 30
    assert step.wait_seconds == 1.5
    assert step.requires_confirmation is True


def test_wait_ocr_step_validates_anchor_in_selected_view() -> None:
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "device_1",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {"view_id": "main", "anchors": [_ocr_anchor("main_status")]},
                {
                    "view_id": "dialog_reset_done",
                    "anchors": [_ocr_anchor("reset_done_text")],
                },
            ],
        }
    )
    workflow = WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id="wf_wait_ocr",
            author="test",
            anchor_profile="device_1",
            lifecycle_state="Draft",
        ),
        steps=[
            WorkflowStep(
                id="wait_for_reset_done",
                action="wait",
                view_id="dialog_reset_done",
                anchor_id="reset_done_text",
                expected_text="复位结束",
                match_mode="contains",
                timeout_seconds=30,
            )
        ],
    )

    assert validate_workflow_against_anchors(workflow, profile) == []


def test_wait_ocr_validation_rejects_anchor_from_different_view() -> None:
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "device_1",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {"view_id": "main", "anchors": [_ocr_anchor("main_status")]},
                {
                    "view_id": "dialog_reset_done",
                    "anchors": [_ocr_anchor("reset_done_text")],
                },
            ],
        }
    )
    workflow = WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id="wf_wait_ocr",
            author="test",
            anchor_profile="device_1",
            lifecycle_state="Draft",
        ),
        steps=[
            WorkflowStep(
                id="wrong_wait_view",
                action="wait",
                view_id="main",
                anchor_id="reset_done_text",
                expected_text="复位结束",
                match_mode="contains",
            )
        ],
    )

    issues = validate_workflow_against_anchors(workflow, profile)

    assert (
        "step wrong_wait_view: anchor_id 'reset_done_text' is not in view 'main'"
        in issues
    )


def test_exception_rules_serialize_with_profile() -> None:
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "device_1",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {"view_id": "main", "anchors": [_anchor("start")]},
                {
                    "view_id": "dialog_connection_failed",
                    "anchors": [_ocr_anchor("connection_failed_text")],
                },
            ],
            "exception_rules": [
                {
                    "id": "connection_failed",
                    "view_id": "dialog_connection_failed",
                    "anchor_id": "connection_failed_text",
                    "expected_text": "连接失败",
                    "match_mode": "contains",
                    "ignore_case": False,
                    "normalize_text": True,
                    "min_confidence": 0.7,
                    "blocking": True,
                    "message": "设备连接失败，请人工处理",
                }
            ],
        }
    )

    payload = profile.model_dump(mode="json", exclude_none=True)

    assert payload["exception_rules"][0]["id"] == "connection_failed"
    assert payload["exception_rules"][0]["expected_text"] == "连接失败"
