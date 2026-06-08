"""Process bootstrap helpers for runtime and desktop entry points.

This is the composition root: it wires concrete adapters to the application
services and builds the runtime API. Adapter selection (stub vs. real) lives
here so the inner layers stay free of provider choices.
"""

from __future__ import annotations

from pathlib import Path

from smartaccess.runtime.adapters import (
    DeepSeekWorkflowGenerator,
    FileArtifactStore,
    SpecLabOSPlatformClient,
    StubAutomationProvider,
    StubPlatformClient,
    StubVisionProvider,
    TemplatePromptWorkflowGenerator,
    UdpProcessExecutorClient,
    Win32AutomationProvider,
)
from smartaccess.runtime.adapters.inmemory import (
    EchoInstructionGenerator,
    StubProcessExecutorClient,
)
from smartaccess.runtime.application import (
    CalibrationService,
    EvaluationService,
    ExperimentService,
    IncidentService,
    PlatformSyncService,
    RunSessionService,
    TemplateService,
    WorkflowService,
    WorkspaceService,
)
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.runtime.orchestration import Executor, Observer, RecoveryEngine
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.events import EventBus

_DEFAULT_UDP_HOST = "127.0.0.1"
_DEFAULT_UDP_PORT = 8889
_DEFAULT_EVAL_CASES = Path("ai/harness/evals/cases")


def build_experiment_service(
    settings: AppSettings | None = None,
    *,
    use_udp: bool = False,
) -> ExperimentService:
    """Assemble :class:`ExperimentService` with adapters chosen by ``use_udp``."""

    settings = settings or AppSettings.from_env()
    host = settings.udp_host or _DEFAULT_UDP_HOST
    port = settings.udp_port or _DEFAULT_UDP_PORT
    udp_target = {"host": host, "port": port}
    executor = (
        UdpProcessExecutorClient(host=host, port=port)
        if use_udp
        else StubProcessExecutorClient()
    )
    return ExperimentService(
        instruction_generator=EchoInstructionGenerator(),
        executor_client=executor,
        udp_target=udp_target,
    )


def build_edge_app(settings: AppSettings | None = None, *, use_udp: bool = False):
    """Build the device-side Edge API (FastAPI) ready to serve."""

    from smartaccess.runtime.api.edge import create_edge_app

    settings = settings or AppSettings.from_env()
    return create_edge_app(build_experiment_service(settings, use_udp=use_udp))


def serve_edge_api(settings: AppSettings | None = None, *, use_udp: bool = True) -> None:
    """Run the Edge API with uvicorn (blocking). Intended as a process entry point."""

    import uvicorn

    settings = settings or AppSettings.from_env()
    uvicorn.run(
        build_edge_app(settings, use_udp=use_udp),
        host=settings.edge_api_host,
        port=settings.edge_api_port,
    )


def build_runtime_facade(
    settings: AppSettings | None = None,
    *,
    use_real: bool = False,
    seed_demo: bool = False,
    eval_cases_dir: Path | None = None,
) -> RuntimeFacade:
    """Compose the full runtime: adapters + services + orchestrator."""

    settings = settings or AppSettings.from_env()
    workspace_dir = Path(settings.workspace_dir)
    event_bus = EventBus()

    automation = _build_automation(settings, use_real=use_real)
    vision = StubVisionProvider()
    platform = _build_platform(settings, use_real=use_real)
    artifact_store = FileArtifactStore(workspace_dir)
    draft_generator = _build_workflow_generator(settings, use_real=use_real)

    calibration = CalibrationService(automation=automation, workspace_dir=workspace_dir)
    workflow = WorkflowService(draft_generator=draft_generator, workspace_dir=workspace_dir)
    run_sessions = RunSessionService(artifact_store=artifact_store, event_bus=event_bus)
    incidents = IncidentService(event_bus=event_bus)
    template = TemplateService(
        platform=platform, workspace_dir=workspace_dir, event_bus=event_bus
    )
    platform_sync = PlatformSyncService(platform=platform, event_bus=event_bus)
    workspace = WorkspaceService(
        calibration=calibration,
        run_sessions=run_sessions,
        incidents=incidents,
        templates=template,
        platform_sync=platform_sync,
    )
    evaluation = EvaluationService(cases_dir=eval_cases_dir or _DEFAULT_EVAL_CASES)

    facade = RuntimeFacade(
        event_bus=event_bus,
        calibration=calibration,
        workflow=workflow,
        template=template,
        run_sessions=run_sessions,
        incidents=incidents,
        platform_sync=platform_sync,
        workspace=workspace,
        evaluation=evaluation,
        executor=Executor(automation),
        observer=Observer(vision),
        recovery=RecoveryEngine(),
    )

    if seed_demo:
        _seed_demo(facade)
    return facade


def _build_automation(settings: AppSettings, *, use_real: bool):
    if use_real or settings.automation_provider == "real":
        return Win32AutomationProvider()
    return StubAutomationProvider()


def _build_platform(settings: AppSettings, *, use_real: bool):
    if (use_real or settings.platform_provider == "real") and settings.speclabos_base_url:
        return SpecLabOSPlatformClient(
            base_url=str(settings.speclabos_base_url),
            api_key=settings.speclabos_api_key,
            timeout_seconds=settings.speclabos_timeout_seconds,
        )
    return StubPlatformClient()


def _build_workflow_generator(settings: AppSettings, *, use_real: bool):
    if (use_real or settings.workflow_generator_provider == "deepseek") and settings.deepseek_api_key:
        return DeepSeekWorkflowGenerator(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )
    return TemplatePromptWorkflowGenerator()


def _seed_demo(facade: RuntimeFacade) -> None:
    """Populate one instrument + one workflow so the UI shows real data."""

    device_id = "potentiostat_win_01"
    facade.create_calibration(
        device_id=device_id,
        title_contains="ElectroChem Console",
        anchors=[
            {
                "id": "anchor_start_button",
                "type": "button",
                "roi": {"x": 40, "y": 40, "width": 160, "height": 48},
                "normalized_roi": {"x": 0.1, "y": 0.08, "width": 0.2, "height": 0.08},
                "action_bindings": [{"action": "click", "requires_confirmation": True}],
                "vision_mode": "none",
                "confidence_threshold": 0.8,
            },
            {
                "id": "anchor_voltage_input",
                "type": "input",
                "roi": {"x": 220, "y": 132, "width": 140, "height": 42},
                "normalized_roi": {"x": 0.28, "y": 0.22, "width": 0.18, "height": 0.07},
                "action_bindings": [{"action": "type", "default_value": "4.20"}],
                "vision_mode": "none",
            },
            {
                "id": "roi_voltage_value",
                "type": "observation",
                "roi": {"x": 320, "y": 182, "width": 180, "height": 56},
                "normalized_roi": {"x": 0.4, "y": 0.3, "width": 0.22, "height": 0.09},
                "vision_mode": "ocr",
                "confidence_threshold": 0.7,
            },
        ],
        actions=["click", "type", "hotkey", "wait_until"],
        safety_limits={
            "max_voltage": 5.0,
            "min_voltage": 0.0,
            "requires_manual_confirm_for": ["start_run"],
            "fields": [
                {
                    "field_id": "start_run",
                    "label": "启动运行",
                    "value_type": "bool",
                    "requires_confirmation": True,
                    "risk_level": "high",
                    "applies_to_steps": ["start_run"],
                }
            ],
        },
        capture_width=1280,
        capture_height=860,
    )
    facade.generate_workflow(
        "对电池做一次标准循环：打开方法编辑器，设定电压 4.20V，启动并等待运行状态。",
        {
            "workflow_id": "wf_battery_cycle_demo",
            "instrument_profile": device_id,
            "experiment_type": "battery_cycle_test",
        },
    )


def run_desktop(settings: AppSettings | None = None) -> int:
    """Build the runtime facade and launch the PyQt6 desktop workbench."""

    from smartaccess.desktop.shell.app import run_app

    facade = build_runtime_facade(settings, seed_demo=True)
    return run_app(facade)
