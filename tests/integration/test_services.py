"""SmartAccess 服务层集成测试。"""

from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.adapters.platform_stub import StubPlatformClient
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.template_service import TemplateService
from smartaccess.runtime.application.workflow_service import WorkflowService
from smartaccess.runtime.domain.incident import IncidentType
from smartaccess.runtime.domain.template import TemplateVersionStatus
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowStep,
)
from smartaccess.shared.events import EventBus, RuntimeEventName

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


def _anchor(anchor_id: str) -> dict:
    """构造测试锚点。

    Args:
        anchor_id: 锚点 ID。

    Returns:
        锚点原始字典。
    """

    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 10, "y": 10, "width": 80, "height": 32},
            "normalized": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
        },
        "observe_region": {
            "pixel": {"x": 120, "y": 10, "width": 120, "height": 32},
            "normalized": {"x": 0.12, "y": 0.01, "width": 0.12, "height": 0.03},
        },
        "supported_actions": ["click"],
        "vision_mode": "ocr",
    }


def _workflow(workflow_id: str = "wf_test") -> WorkflowContract:
    """构造测试工作流。

    Args:
        workflow_id: 工作流 ID。

    Returns:
        工作流契约。
    """

    return WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id=workflow_id,
            author="test",
            anchor_profile=DEVICE_ID,
            lifecycle_state="Draft",
        ),
        steps=[
            WorkflowStep(
                id="start_and_wait",
                action="click",
                anchor_id="status_button",
                expected_text="Running",
                match_mode="contains",
                timeout_seconds=5.0,
            )
        ],
        outputs=[WorkflowOutput(key="run_status", source="status_button")],
    )


def test_facade_writes_anchor_profile_and_standardizes_workflow(tmp_path: Path) -> None:
    """验证门面能保存锚点配置并校验工作流。"""

    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    profile = facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="ElectroChem Console",
        capture_width=1322,
        capture_height=914,
        anchors=[_anchor("status_button")],
    )
    workflow = facade.save_workflow(_workflow())

    assert (tmp_path / "anchors" / DEVICE_ID / "anchors.yaml").exists()
    assert profile.profile_id == DEVICE_ID
    assert facade.standardize(workflow).ok


def test_workflow_update_persists_outputs(tmp_path: Path) -> None:
    """验证工作流更新会持久化 outputs。"""

    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="ElectroChem Console",
        capture_width=1322,
        capture_height=914,
        anchors=[_anchor("status_button")],
    )
    workflow = facade.save_workflow(_workflow("wf_outputs"))
    updated = workflow.model_copy(deep=True)
    updated.outputs = [WorkflowOutput(key="selected_contact", source="status_button")]

    saved = facade.save_workflow(updated)
    reloaded = load_yaml_contract(
        tmp_path / "workflows" / "wf_outputs" / "draft.yaml",
        WorkflowContract,
    )

    assert [(item.key, item.source) for item in saved.outputs] == [
        ("selected_contact", "status_button")
    ]
    assert [(item.key, item.source) for item in reloaded.outputs] == [
        ("selected_contact", "status_button")
    ]


def test_template_publish_supersede_and_rollback(tmp_path: Path) -> None:
    """验证模板发布、替代和回滚状态流转。"""

    bus = EventBus()
    anchors = build_runtime_facade(AppSettings(workspace_dir=tmp_path)).providers()["anchors"]
    workflows = WorkflowService(
        workspace_dir=tmp_path,
        anchors=anchors,
        draft_generator=None,
    )
    svc = TemplateService(
        platform=StubPlatformClient(),
        workspace_dir=tmp_path,
        event_bus=bus,
        source_device_id="pc-workstation",
    )
    v1 = workflows.register(_workflow("w1"))
    v1.metadata.template_id = "t1"
    v1.metadata.template_version = "1.0.0"
    svc.publish(v1)

    v2 = v1.model_copy(deep=True)
    v2.metadata.template_version = "1.1.0"
    svc.publish(v2)

    versions = {item.identity.template_version: item for item in svc.list_versions("t1")}
    assert versions["1.0.0"].status == TemplateVersionStatus.SUPERSEDED
    assert versions["1.1.0"].status == TemplateVersionStatus.PUBLISHED
    assert versions["1.1.0"].workflow_id == "w1"

    svc.rollback("t1", "1.0.0")
    versions = {item.identity.template_version: item.status for item in svc.list_versions("t1")}
    assert versions["1.0.0"] == TemplateVersionStatus.PUBLISHED
    assert versions["1.1.0"] == TemplateVersionStatus.ROLLED_BACK


def test_platform_outbox_retries_then_fails(tmp_path: Path) -> None:
    """验证平台 outbox 重试失败后发出失败事件。"""

    bus = EventBus()
    failures: list[RuntimeEventName] = []
    bus.subscribe(lambda event: failures.append(event.name))
    sync = PlatformSyncService(
        platform=StubPlatformClient(offline=True),
        event_bus=bus,
        workspace_dir=tmp_path,
        max_attempts=2,
    )

    sync.enqueue("status", {"run": "s1"})

    assert sync.sync().pending == 1
    stats = sync.sync()
    assert stats.pending == 0
    assert stats.failed == 1
    assert RuntimeEventName.PLATFORM_SYNC_FAILED in failures


def test_incident_manual_confirm_flow() -> None:
    """验证人工确认异常的事件流。"""

    bus = EventBus()
    seen: list[RuntimeEventName] = []
    bus.subscribe(lambda event: seen.append(event.name))
    svc = IncidentService(event_bus=bus)

    incident = svc.open(
        session_id="s1",
        step_id="start_run",
        incident_type=IncidentType.SAFETY_LIMIT_VIOLATION,
        detail="参数越界",
    )
    svc.confirm(incident.incident_id)

    assert incident.requires_manual_confirm
    assert incident.resolved
    assert RuntimeEventName.RUN_BLOCKED in seen
    assert RuntimeEventName.RUN_RECOVERED in seen


def test_udp_workspace_draft_standardizes(tmp_path: Path) -> None:
    """验证 workspace 中的 UDP 示例仍可标准化。"""

    base = REPO_ROOT / "workspace"
    profile_path = base / "anchors" / "serial_debug_assistant_udp" / "anchors.yaml"
    workflow_path = base / "workflows" / "wf_serial_debug_assistant_udp_send" / "draft.yaml"
    if not profile_path.exists() or not workflow_path.exists():
        return
    profile = load_yaml_contract(profile_path, AnchorsContract)
    workflow = load_yaml_contract(workflow_path, WorkflowContract)
    dump_yaml_contract(profile, tmp_path / "anchors" / profile.profile_id / "anchors.yaml")
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))

    check = facade.standardize(workflow)

    assert check.ok, check.issues


def test_capability_example_assets_are_standardized(tmp_path: Path) -> None:
    """验证能力示例契约仍可通过标准化检查。"""

    for example_dir in ("serial_debug_assistant_udp",):
        base = REPO_ROOT / "docs" / "contracts" / "examples" / example_dir
        if not (base / "anchors.yaml").exists() or not (base / "workflow.yaml").exists():
            continue
        profile = load_yaml_contract(base / "anchors.yaml", AnchorsContract)
        workflow = load_yaml_contract(base / "workflow.yaml", WorkflowContract)
        dump_yaml_contract(profile, tmp_path / "anchors" / profile.profile_id / "anchors.yaml")
        facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))

        check = facade.standardize(workflow)

        assert workflow.metadata.anchor_profile == profile.profile_id
        assert check.ok, check.issues
