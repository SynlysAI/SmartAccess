from __future__ import annotations

from pathlib import Path

from smartaccess.shared.contracts import (
    AnchorsContract,
    EvalCaseContract,
    PlatformAdapterContract,
    RunTraceRecord,
    WorkflowContract,
    dump_jsonl_contracts,
    dump_yaml_contract,
    load_jsonl_contracts,
    load_yaml_contract,
    validate_workflow_against_anchors,
)
from smartaccess.shared.contracts.validation import validate_device_id

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_core_contract_examples() -> None:
    anchors = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/anchors.yaml",
        AnchorsContract,
    )
    workflow = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/workflow.yaml",
        WorkflowContract,
    )
    platform_adapter = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/platform_adapter.yaml",
        PlatformAdapterContract,
    )
    eval_case = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/eval_case.yaml",
        EvalCaseContract,
    )
    run_trace = load_jsonl_contracts(
        REPO_ROOT / "docs/contracts/examples/run_trace.jsonl",
        RunTraceRecord,
    )

    assert anchors.profile_id == "氟基-2236实验室-元能极片电阻仪-01"
    assert workflow.metadata.anchor_profile == anchors.profile_id
    assert workflow.metadata.template_id == "tpl_battery_cycle_standard"
    assert platform_adapter.endpoint_map.fetch_template.endswith("{template_version}")
    assert eval_case.scenario.id == "eval_platform_sync_01"
    assert len(run_trace) == 2
    assert run_trace[1].status == "success"
    assert run_trace[1].actual_text == "Status: Running"


def test_package_exports_platform_and_eval_contracts() -> None:
    platform_adapter = PlatformAdapterContract.model_validate(
        {
            "base_url": "http://example.test/api",
            "endpoint_map": {"fetch_template": "/templates/{template_version}"},
        }
    )
    eval_case = EvalCaseContract.model_validate(
        {
            "scenario": {"id": "case_01"},
            "inputs": {},
            "pass_criteria": ["loads"],
        }
    )

    assert platform_adapter.endpoint_map.fetch_template == "/templates/{template_version}"
    assert eval_case.scenario.id == "case_01"


def test_increment_rule_extended_fields_are_backward_compatible() -> None:
    old_style = WorkflowContract.model_validate(
        {
            "metadata": {
                "workflow_id": "wf_old_increment",
                "anchor_profile": "device_1",
                "author": "tester",
                "lifecycle_state": "Draft",
            },
            "steps": [
                {
                    "id": "sample",
                    "anchor_id": "input",
                    "action": "type",
                    "input_mode": "incrementing",
                    "increment_rule": {},
                }
            ],
        }
    )
    rule = old_style.steps[0].increment_rule

    assert rule is not None
    assert rule.sequence_key == "default"
    assert rule.date_format == "%Y%m%d"
    assert rule.min_value is None
    assert rule.max_value is None
    assert rule.cycle is False

    new_style = WorkflowContract.model_validate(
        {
            "metadata": old_style.metadata.model_dump(mode="json"),
            "steps": [
                {
                    "id": "sample",
                    "anchor_id": "input",
                    "action": "type",
                    "input_mode": "incrementing",
                    "increment_rule": {
                        "pattern": "{date}-{counter:02d}",
                        "sequence_key": "sample_name",
                        "date_format": "%Y-%m-%d",
                        "start": 0,
                        "width": 2,
                        "min_value": 0,
                        "max_value": 100,
                        "cycle": True,
                    },
                }
            ],
        }
    )

    dumped = new_style.model_dump(mode="json", exclude_none=True)
    assert dumped["steps"][0]["increment_rule"]["sequence_key"] == "sample_name"
    assert dumped["steps"][0]["increment_rule"]["date_format"] == "%Y-%m-%d"
    assert dumped["steps"][0]["increment_rule"]["cycle"] is True


def test_new_device_id_validation_rule() -> None:
    assert validate_device_id("氟基-2236实验室-元能极片电阻仪-01") == []
    assert validate_device_id("d1")
    assert validate_device_id("氟基-2236实验室-元能极片电阻仪")
    assert validate_device_id('氟基-2236实验室-元能/极片电阻仪-01')


def test_load_eval_harness_cases() -> None:
    case_dir = REPO_ROOT / "ai/harness/evals/cases"
    case_files = sorted(case_dir.glob("*.yaml"))

    assert case_files

    for case_file in case_files:
        eval_case = load_yaml_contract(case_file, EvalCaseContract)
        assert eval_case.scenario.id
        assert eval_case.pass_criteria


def test_load_capability_example_contracts() -> None:
    for example_dir in ("serial_debug_assistant_udp", "windows_calculator"):
        base = REPO_ROOT / "docs/contracts/examples" / example_dir
        anchors = load_yaml_contract(base / "anchors.yaml", AnchorsContract)
        workflow = load_yaml_contract(base / "workflow.yaml", WorkflowContract)

        assert workflow.metadata.anchor_profile == anchors.profile_id
        assert workflow.steps
        assert any(step.match_mode != "none" for step in workflow.steps)


def test_contract_round_trip(tmp_path: Path) -> None:
    anchors = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/anchors.yaml",
        AnchorsContract,
    )
    workflow = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/workflow.yaml",
        WorkflowContract,
    )
    run_trace = load_jsonl_contracts(
        REPO_ROOT / "docs/contracts/examples/run_trace.jsonl",
        RunTraceRecord,
    )

    anchors_path = dump_yaml_contract(anchors, tmp_path / "anchors.yaml")
    workflow_path = dump_yaml_contract(workflow, tmp_path / "workflow.yaml")
    run_trace_path = dump_jsonl_contracts(run_trace, tmp_path / "run_trace.jsonl")

    reloaded_anchors = load_yaml_contract(anchors_path, AnchorsContract)
    reloaded_workflow = load_yaml_contract(workflow_path, WorkflowContract)
    reloaded_trace = load_jsonl_contracts(run_trace_path, RunTraceRecord)

    assert reloaded_anchors.model_dump(mode="json", exclude_none=True) == anchors.model_dump(mode="json", exclude_none=True)
    assert reloaded_workflow.model_dump(mode="json", exclude_none=True) == workflow.model_dump(mode="json", exclude_none=True)
    assert reloaded_trace == run_trace


def test_new_anchor_and_workflow_examples_use_simplified_model() -> None:
    anchors = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/anchors.yaml",
        AnchorsContract,
    )
    workflow = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/workflow.yaml",
        WorkflowContract,
    )

    dumped_anchors = anchors.model_dump(mode="json", exclude_none=True)
    dumped_workflow = workflow.model_dump(mode="json", exclude_none=True)
    allowed_actions = {"click", "double_click", "type", "hotkey", "press_enter", "ocr"}

    assert all("type" not in anchor for anchor in dumped_anchors["anchors"])
    assert all(set(anchor["supported_actions"]) <= allowed_actions for anchor in dumped_anchors["anchors"])
    assert all(step["action"] in allowed_actions for step in dumped_workflow["steps"])
    assert not any(step["action"] in {"wait", "wait_until", "screenshot_check"} for step in dumped_workflow["steps"])


def test_legacy_anchor_types_are_read_compatible() -> None:
    anchors = AnchorsContract.model_validate(
        {
            "profile_id": "legacy_device",
            "window_signature": {"title_contains": "Legacy"},
            "anchors": [
                {
                    "id": "legacy_button",
                    "type": "button",
                    "roi": {"x": 10, "y": 10, "width": 20, "height": 20},
                    "normalized_roi": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                    "action_bindings": [{"action": "double_click"}],
                    "vision_mode": "template",
                },
                {
                    "id": "legacy_status",
                    "type": "observation",
                    "roi": {"x": 30, "y": 30, "width": 40, "height": 20},
                    "normalized_roi": {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.2},
                    "action_bindings": [{"action": "wait_until"}],
                    "vision_mode": "ocr",
                },
            ],
        }
    )

    assert anchors.anchor_map()["legacy_button"].supported_actions == ["double_click"]
    assert anchors.anchor_map()["legacy_status"].observe_region is not None
    dumped = anchors.model_dump(mode="json", exclude_none=True)
    assert all("type" not in anchor for anchor in dumped["anchors"])


def test_legacy_workflow_steps_are_normalized() -> None:
    workflow = WorkflowContract.model_validate(
        {
            "metadata": {
                "workflow_id": "wf_legacy",
                "anchor_profile": "legacy_device",
                "author": "test",
                "lifecycle_state": "Draft",
            },
            "steps": [
                {"id": "open", "action": "double_click", "target": "start"},
                {
                    "id": "wait_running",
                    "action": "wait_until",
                    "target": "status",
                    "condition": {
                        "operator": "contains",
                        "expected": "Running",
                        "timeout_seconds": 5,
                    },
                },
            ],
        }
    )

    assert [step.action for step in workflow.steps] == ["double_click"]
    assert workflow.steps[-1].expected_text == "Running"
    assert workflow.steps[-1].match_mode == "contains"
    assert workflow.steps[-1].timeout_seconds == 5


def test_unmergeable_legacy_wait_becomes_migration_error() -> None:
    workflow = WorkflowContract.model_validate(
        {
            "metadata": {
                "workflow_id": "wf_bad_legacy",
                "anchor_profile": "legacy_device",
                "author": "test",
                "lifecycle_state": "Draft",
            },
            "steps": [
                {
                    "id": "wait_first",
                    "action": "wait_until",
                    "target": "status",
                    "condition": {"operator": "not_empty", "timeout_seconds": 2},
                }
            ],
        }
    )

    assert workflow.steps == []
    assert len(workflow.migration_errors) == 1
    assert "rebind" in workflow.migration_errors[0].reason


def test_ocr_validation_requires_observe_region_and_expected_text() -> None:
    anchors = AnchorsContract.model_validate(
        {
            "profile_id": "device",
            "window_signature": {"title_contains": "Demo"},
            "anchors": [
                {
                    "id": "input",
                    "action_region": {
                        "pixel": {"x": 0, "y": 0, "width": 10, "height": 10},
                        "normalized": {"x": 0, "y": 0, "width": 0.1, "height": 0.1},
                    },
                    "supported_actions": ["click"],
                },
                {
                    "id": "status",
                    "action_region": {
                        "pixel": {"x": 0, "y": 0, "width": 10, "height": 10},
                        "normalized": {"x": 0, "y": 0, "width": 0.1, "height": 0.1},
                    },
                    "observe_region": {
                        "pixel": {"x": 10, "y": 0, "width": 20, "height": 10},
                        "normalized": {"x": 0.1, "y": 0, "width": 0.2, "height": 0.1},
                    },
                    "supported_actions": ["click"],
                },
            ],
        }
    )
    workflow = WorkflowContract.model_validate(
        {
            "metadata": {
                "workflow_id": "wf_bad_ocr",
                "anchor_profile": "device",
                "author": "test",
                "lifecycle_state": "Draft",
            },
            "steps": [
                {"id": "missing_observe", "anchor_id": "input", "action": "click", "match_mode": "not_empty"},
                {"id": "missing_expected", "anchor_id": "status", "action": "click", "match_mode": "contains"},
            ],
        }
    )

    issues = validate_workflow_against_anchors(workflow, anchors)

    assert any("requires observe_region" in issue for issue in issues)
    assert any("expected_text is required" in issue for issue in issues)
