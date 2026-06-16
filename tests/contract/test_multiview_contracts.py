from __future__ import annotations

from smartaccess.shared.contracts.anchors import AnchorsContract
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
