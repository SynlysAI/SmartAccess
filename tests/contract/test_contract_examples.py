from __future__ import annotations

from pathlib import Path

from smartaccess.shared.contracts import (
    EvalCaseContract,
    InstrumentProfileContract,
    PlatformAdapterContract,
    RunTraceRecord,
    WorkflowContract,
    dump_jsonl_contracts,
    dump_yaml_contract,
    load_jsonl_contracts,
    load_yaml_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_core_contract_examples() -> None:
    workflow = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/workflow.yaml",
        WorkflowContract,
    )
    instrument_profile = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/instrument_profile.yaml",
        InstrumentProfileContract,
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

    assert workflow.metadata.template_id == "tpl_battery_cycle_standard"
    assert instrument_profile.device_id == "potentiostat_win_01"
    assert platform_adapter.endpoint_map.fetch_template.endswith("{template_version}")
    assert eval_case.scenario.id == "eval_platform_sync_01"
    assert len(run_trace) == 2
    assert run_trace[1].result.status == "success"


def test_load_eval_harness_cases() -> None:
    case_dir = REPO_ROOT / "ai/harness/evals/cases"
    case_files = sorted(case_dir.glob("*.yaml"))

    assert case_files

    for case_file in case_files:
        eval_case = load_yaml_contract(case_file, EvalCaseContract)
        assert eval_case.scenario.id
        assert eval_case.pass_criteria


def test_contract_round_trip(tmp_path: Path) -> None:
    workflow = load_yaml_contract(
        REPO_ROOT / "docs/contracts/examples/workflow.yaml",
        WorkflowContract,
    )
    run_trace = load_jsonl_contracts(
        REPO_ROOT / "docs/contracts/examples/run_trace.jsonl",
        RunTraceRecord,
    )

    workflow_path = dump_yaml_contract(workflow, tmp_path / "workflow.yaml")
    run_trace_path = dump_jsonl_contracts(run_trace, tmp_path / "run_trace.jsonl")

    reloaded_workflow = load_yaml_contract(workflow_path, WorkflowContract)
    reloaded_trace = load_jsonl_contracts(run_trace_path, RunTraceRecord)

    assert reloaded_workflow == workflow
    assert reloaded_trace == run_trace
