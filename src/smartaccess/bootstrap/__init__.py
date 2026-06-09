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
    LocalVisionProvider,
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
from smartaccess.runtime.application.ai_runtime_store import AIRuntimeStore
from smartaccess.runtime.application.facade import AIAssistantStatus, RuntimeFacade
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
    automation_provider: str = "stub",
    vision_provider: str = "stub",
    platform_provider: str = "stub",
    eval_cases_dir: Path | None = None,
) -> RuntimeFacade:
    """Compose the full runtime: adapters + services + orchestrator.

    Each provider accepts ``"real"`` (default in desktop), ``"stub"`` (tests), or
    ``"local"`` (vision).  If a real provider's dependencies are missing the call
    raises ``RuntimeError`` immediately — no silent fallback.
    """

    settings = settings or AppSettings.from_env()
    workspace_dir = Path(settings.workspace_dir)
    event_bus = EventBus()

    automation = _build_automation(settings, mode=automation_provider)
    vision = _build_vision(settings, mode=vision_provider, workspace_dir=workspace_dir)
    platform = _build_platform(settings, mode=platform_provider)
    artifact_store = FileArtifactStore(workspace_dir)
    draft_generator = _build_workflow_generator(settings)

    # AI runtime knowledge store — persistent learning across generations
    ai_store = AIRuntimeStore(workspace_dir)

    calibration = CalibrationService(automation=automation, workspace_dir=workspace_dir)
    workflow = WorkflowService(
        draft_generator=draft_generator, workspace_dir=workspace_dir, ai_store=ai_store
    )
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
        workflows=workflow,
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
        ai_assistant_status=_build_ai_status(settings, draft_generator),
    )

    return facade


def _build_ai_status(settings: AppSettings, draft_generator) -> AIAssistantStatus:
    label = "DeepSeek" if "DeepSeek" in type(draft_generator).__name__ else "模板生成器"
    if label == "DeepSeek":
        return AIAssistantStatus(
            provider="DeepSeek",
            model=settings.deepseek_model,
            status="已配置" if settings.deepseek_configured else "未配置",
            detail=f"base_url={settings.deepseek_base_url}",
        )
    return AIAssistantStatus(
        provider="模板生成器",
        model="内置模板规则",
        status="模拟模式",
        detail="未接入在线模型，使用本地模板生成草稿",
    )


def _build_automation(settings: AppSettings, *, mode: str):
    if mode == "real" or settings.automation_provider == "real":
        return Win32AutomationProvider()
    return StubAutomationProvider()


def _build_vision(settings: AppSettings, *, mode: str, workspace_dir: Path):
    if mode == "local":
        # Fail fast if PaddleOCR or OpenCV is missing — never silently fall back.
        return LocalVisionProvider(workspace_dir=workspace_dir)
    return StubVisionProvider()


def _build_platform(settings: AppSettings, *, mode: str):
    if (mode == "real" or settings.platform_provider == "real") and settings.speclabos_base_url:
        return SpecLabOSPlatformClient(
            base_url=str(settings.speclabos_base_url),
            api_key=settings.speclabos_api_key,
            timeout_seconds=settings.speclabos_timeout_seconds,
        )
    return StubPlatformClient()


def _build_workflow_generator(settings: AppSettings):
    if settings.workflow_generator_provider == "deepseek" and settings.deepseek_api_key:
        return DeepSeekWorkflowGenerator(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )
    return TemplatePromptWorkflowGenerator()


def run_desktop(settings: AppSettings | None = None) -> int:
    """Build the runtime facade and launch the PyQt6 desktop workbench."""

    from smartaccess.desktop.shell.app import run_app

    settings = settings or AppSettings.from_env()
    facade = build_runtime_facade(
        settings,
        automation_provider="real",
        vision_provider="local",
        platform_provider="real" if settings.speclabos_base_url else "stub",
    )
    llm_provider = "DeepSeek" if settings.deepseek_configured else "模板生成器"
    return run_app(
        facade,
        provider_modes={
            "automation": "real",
            "vision": "local",
            "llm": llm_provider,
        },
    )
