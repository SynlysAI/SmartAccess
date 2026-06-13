"""SmartAccess v2 运行时依赖装配。"""

from __future__ import annotations

from smartaccess_v2.runtime.adapters import (
    EchoInstructionGenerator,
    FileArtifactStore,
    LocalVisionProvider,
    SmartAccessAiGenerator,
    SpecLabOSPlatformClient,
    StubAutomationProvider,
    StubPlatformClient,
    StubProcessExecutorClient,
    StubVisionProvider,
    UdpProcessExecutorClient,
    Win32AutomationProvider,
)
from smartaccess_v2.runtime.application.anchor_service import AnchorService
from smartaccess_v2.runtime.application.experiment_service import ExperimentService
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.runtime.application.incident_service import IncidentService
from smartaccess_v2.runtime.application.migration_service import MigrationService
from smartaccess_v2.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess_v2.runtime.application.run_session_service import RunSessionService
from smartaccess_v2.runtime.application.template_service import TemplateService
from smartaccess_v2.runtime.application.workflow_service import WorkflowService
from smartaccess_v2.runtime.application.workspace_service import WorkspaceService
from smartaccess_v2.runtime.orchestration import (
    Executor,
    Observer,
    Orchestrator,
    RecoveryEngine,
)
from smartaccess_v2.shared.config.settings import AppSettings
from smartaccess_v2.shared.events.bus import EventBus
from smartaccess_v2.shared.logging import get_logger


def build_runtime_facade(settings: AppSettings) -> RuntimeFacade:
    """按配置创建运行时门面。

    Args:
        settings: 应用配置。

    Returns:
        运行时门面。
    """

    event_bus = EventBus(get_logger())
    automation = _build_automation(settings)
    vision = _build_vision(settings)
    platform = _build_platform(settings)
    artifacts = FileArtifactStore(settings.workspace_dir)
    ai_generator = _build_ai_generator(settings)
    anchors = AnchorService(workspace_dir=settings.workspace_dir)
    workflows = WorkflowService(
        workspace_dir=settings.workspace_dir,
        anchors=anchors,
        draft_generator=ai_generator,
    )
    run_sessions = RunSessionService(artifact_store=artifacts, event_bus=event_bus)
    incidents = IncidentService(event_bus=event_bus)
    platform_sync = PlatformSyncService(
        platform=platform,
        event_bus=event_bus,
        workspace_dir=settings.workspace_dir,
    )
    templates = TemplateService(
        platform=platform,
        workspace_dir=settings.workspace_dir,
        event_bus=event_bus,
    )
    migration = MigrationService(workspace_dir=settings.workspace_dir)
    workspace = WorkspaceService(
        anchors=anchors,
        workflows=workflows,
        templates=templates,
        run_sessions=run_sessions,
        incidents=incidents,
        platform_sync=platform_sync,
    )
    orchestrator = Orchestrator(
        executor=Executor(automation),
        observer=Observer(vision),
        recovery=RecoveryEngine(),
        run_sessions=run_sessions,
        incidents=incidents,
    )
    return RuntimeFacade(
        settings=settings,
        event_bus=event_bus,
        automation=automation,
        vision=vision,
        platform=platform,
        artifacts=artifacts,
        anchors=anchors,
        workflows=workflows,
        templates=templates,
        workspace=workspace,
        run_sessions=run_sessions,
        incidents=incidents,
        platform_sync=platform_sync,
        orchestrator=orchestrator,
        migration=migration,
        ai_generator=ai_generator,
    )


def build_experiment_service(
    settings: AppSettings | None = None,
    *,
    use_udp: bool | None = None,
) -> ExperimentService:
    """创建设备侧实验触发服务。

    Args:
        settings: 应用配置；为空时从环境变量读取。
        use_udp: 是否使用 UDP 驱动下游流程主机；为空时根据配置判断。

    Returns:
        实验触发服务。
    """

    settings = settings or AppSettings.from_env()
    enabled = (
        settings.process_executor_provider.lower() == "udp"
        if use_udp is None
        else use_udp
    )
    executor = (
        UdpProcessExecutorClient(
            host=settings.udp_host,
            port=settings.udp_port,
            timeout_s=settings.udp_timeout_seconds,
        )
        if enabled
        else StubProcessExecutorClient()
    )
    return ExperimentService(
        instruction_generator=EchoInstructionGenerator(),
        executor_client=executor,
        udp_target={
            "enabled": enabled,
            "host": settings.udp_host,
            "port": settings.udp_port,
        },
    )


def build_edge_app(settings: AppSettings | None = None, *, use_udp: bool | None = None):
    """创建设备侧 Edge API 应用。

    Args:
        settings: 应用配置；为空时从环境变量读取。
        use_udp: 是否使用 UDP 执行器。

    Returns:
        FastAPI 应用。
    """

    from smartaccess_v2.runtime.api.edge import create_edge_app

    settings = settings or AppSettings.from_env()
    return create_edge_app(build_experiment_service(settings, use_udp=use_udp))


def serve_edge_api(settings: AppSettings | None = None, *, use_udp: bool | None = None) -> None:
    """阻塞启动 Edge API 服务。

    Args:
        settings: 应用配置；为空时从环境变量读取。
        use_udp: 是否使用 UDP 执行器。
    """

    import uvicorn

    settings = settings or AppSettings.from_env()
    uvicorn.run(
        build_edge_app(settings, use_udp=use_udp),
        host=settings.edge_api_host,
        port=settings.edge_api_port,
    )


def _build_automation(settings: AppSettings):
    """创建自动化 provider。"""

    if settings.automation_provider.lower() == "real":
        try:
            return Win32AutomationProvider()
        except Exception:  # noqa: BLE001 - 启动时真实自动化失败可回退 stub
            get_logger().exception("Win32 自动化初始化失败，已回退 Stub")
    return StubAutomationProvider()


def _build_vision(settings: AppSettings):
    """创建视觉 provider。"""

    if settings.vision_provider.lower() == "local":
        try:
            return LocalVisionProvider(workspace_dir=settings.workspace_dir)
        except Exception:  # noqa: BLE001 - 可选 OCR 依赖缺失时回退 stub
            get_logger().exception("本地视觉初始化失败，已回退 Stub")
    return StubVisionProvider(low_confidence_first=False)


def _build_platform(settings: AppSettings):
    """创建平台客户端。"""

    if (
        settings.platform_provider.lower() == "real"
        and settings.speclabos_base_url
    ):
        return SpecLabOSPlatformClient(
            base_url=settings.speclabos_base_url,
            api_key=settings.speclabos_api_key,
            timeout_seconds=settings.speclabos_timeout_seconds,
        )
    return StubPlatformClient()


def _build_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """按配置创建 AI 生成器。"""

    provider = settings.ai_provider.lower().strip()
    if provider == "template":
        return None
    api_key = settings.ai_api_key
    base_url = settings.ai_base_url
    model = settings.ai_model
    timeout = settings.ai_timeout_seconds
    if provider == "deepseek":
        api_key = settings.deepseek_api_key or settings.ai_api_key
        base_url = settings.deepseek_base_url or settings.ai_base_url
        model = settings.deepseek_model or settings.ai_model
        timeout = settings.deepseek_timeout_seconds or settings.ai_timeout_seconds
    if not api_key:
        get_logger().warning("AI provider=%s 未配置 API Key，AI 生成功能未启用", provider)
        return None
    return SmartAccessAiGenerator(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
        timeout_seconds=timeout,
        user_agent=settings.ai_user_agent,
    )
