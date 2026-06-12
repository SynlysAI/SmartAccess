"""Process bootstrap helpers for runtime and desktop entry points."""

from __future__ import annotations

from pathlib import Path

from smartaccess.runtime.adapters import (
    DeepSeekInstrumentProfileGenerator,
    DeepSeekWorkflowGenerator,
    FileArtifactStore,
    LocalVisionProvider,
    OpenAICompatibleInstrumentProfileGenerator,
    OpenAICompatibleWorkflowGenerator,
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
    WorkspaceSettingsStore,
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
    """Compose the full runtime: adapters + services + orchestrator."""

    settings = settings or AppSettings.from_env()
    workspace_dir = Path(settings.workspace_dir)
    event_bus = EventBus()

    automation = _build_automation(settings, mode=automation_provider)
    vision = _build_vision(settings, mode=vision_provider, workspace_dir=workspace_dir)
    platform = _build_platform(settings, mode=platform_provider)
    artifact_store = FileArtifactStore(workspace_dir)
    workspace_settings = WorkspaceSettingsStore(workspace_dir=workspace_dir)
    draft_generator = _build_workflow_generator(settings)
    instrument_draft_generator = _build_instrument_profile_generator(settings)
    ai_store = AIRuntimeStore(workspace_dir)

    calibration = CalibrationService(
        automation=automation,
        workspace_dir=workspace_dir,
        draft_generator=instrument_draft_generator,
    )
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

    return RuntimeFacade(
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
        ai_assistant_status=_build_ai_status(settings),
        workspace_settings=workspace_settings,
    )


def _build_ai_status(settings: AppSettings) -> AIAssistantStatus:
    active_profile = settings.ai_active_profile_config
    if active_profile and active_profile.configured:
        return AIAssistantStatus(
            provider=_provider_label(active_profile.provider),
            model=active_profile.model,
            status="Configured",
            detail=f"base_url={active_profile.base_url}",
            active_profile=active_profile.profile_id,
            profiles=tuple(settings.ai_profile_public_options()),
        )
    return AIAssistantStatus(
        provider="Template",
        model="Built-in template rules",
        status="Local template",
        detail="No online model configured; using local draft rules.",
        active_profile=settings.ai_active_profile,
        profiles=tuple(settings.ai_profile_public_options()),
    )


def _build_automation(settings: AppSettings, *, mode: str):
    if mode == "real" or settings.automation_provider == "real":
        return Win32AutomationProvider()
    return StubAutomationProvider()


def _build_vision(settings: AppSettings, *, mode: str, workspace_dir: Path):
    if mode == "local":
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
    active_profile = settings.ai_active_profile_config
    if active_profile and active_profile.configured:
        if active_profile.provider.lower() == "deepseek":
            return DeepSeekWorkflowGenerator(
                api_key=active_profile.api_key or "",
                base_url=active_profile.base_url,
                model=active_profile.model,
                timeout_seconds=active_profile.timeout_seconds,
                user_agent=active_profile.user_agent,
                profiles=settings.ai_profiles,
                active_profile=active_profile.profile_id,
            )
        return OpenAICompatibleWorkflowGenerator(
            api_key=active_profile.api_key or "",
            base_url=active_profile.base_url,
            model=active_profile.model,
            provider_name=_provider_label(active_profile.provider),
            timeout_seconds=active_profile.timeout_seconds,
            user_agent=active_profile.user_agent,
            profiles=settings.ai_profiles,
            active_profile=active_profile.profile_id,
            wire_api=active_profile.wire_api,
        )
    return TemplatePromptWorkflowGenerator()


def _build_instrument_profile_generator(settings: AppSettings):
    active_profile = settings.ai_active_profile_config
    if active_profile and active_profile.configured:
        if active_profile.provider.lower() == "deepseek":
            return DeepSeekInstrumentProfileGenerator(
                api_key=active_profile.api_key or "",
                base_url=active_profile.base_url,
                model=active_profile.model,
                timeout_seconds=active_profile.timeout_seconds,
                user_agent=active_profile.user_agent,
                profiles=settings.ai_profiles,
                active_profile=active_profile.profile_id,
            )
        return OpenAICompatibleInstrumentProfileGenerator(
            api_key=active_profile.api_key or "",
            base_url=active_profile.base_url,
            model=active_profile.model,
            provider_name=_provider_label(active_profile.provider),
            timeout_seconds=active_profile.timeout_seconds,
            user_agent=active_profile.user_agent,
            profiles=settings.ai_profiles,
            active_profile=active_profile.profile_id,
            wire_api=active_profile.wire_api,
        )
    return None


def _provider_label(provider: str) -> str:
    labels = {
        "deepseek": "DeepSeek",
        "codex": "Codex",
        "openai": "OpenAI",
        "openai-compatible": "OpenAI-compatible",
        "compatible": "OpenAI-compatible",
    }
    return labels.get(provider.lower(), provider)


def _llm_provider_label(settings: AppSettings) -> str:
    active_profile = settings.ai_active_profile_config
    if active_profile and active_profile.configured:
        return f"{_provider_label(active_profile.provider)} / {active_profile.model}"
    return "Template"


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
    return run_app(
        facade,
        provider_modes={
            "automation": "real",
            "vision": "local",
            "llm": _llm_provider_label(settings),
        },
    )
