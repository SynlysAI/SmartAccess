"""SmartAccess 运行时依赖装配。"""

from __future__ import annotations

import json

import pika

from smartaccess.runtime.adapters import (
    ApiVisionProvider,
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
from smartaccess.runtime.application.anchor_service import AnchorService
from smartaccess.runtime.application.experiment_service import ExperimentService
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.migration_service import MigrationService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.run_session_service import (
    IncrementCounterService,
    RunSessionService,
)
from smartaccess.runtime.application.template_service import TemplateService
from smartaccess.runtime.application.workflow_service import WorkflowService
from smartaccess.runtime.application.workspace_service import WorkspaceService
from smartaccess.runtime.orchestration import (
    Executor,
    Observer,
    Orchestrator,
    RecoveryEngine,
)
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.events.bus import EventBus
from smartaccess.shared.logging import configure_logging, get_logger


REMOTE_OCR_MODES = {
    "paddleocr-vl",
    "paddleocr_vl",
    "vl",
    "paddlex",
    "paddlex-ocr",
    "paddlex_ocr",
}


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
    text_ai_generator = _build_text_ai_generator(settings)
    vision_ai_generator = _build_vision_ai_generator(settings)
    anchors = AnchorService(workspace_dir=settings.workspace_dir)
    workflows = WorkflowService(
        workspace_dir=settings.workspace_dir,
        anchors=anchors,
        draft_generator=text_ai_generator,
    )
    run_sessions = RunSessionService(artifact_store=artifacts, event_bus=event_bus)
    increment_counters = IncrementCounterService(settings.workspace_dir)
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
        source_device_id=settings.device_id,
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
        increment_counters=increment_counters,
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
        increment_counters=increment_counters,
        orchestrator=orchestrator,
        migration=migration,
        ai_generator=text_ai_generator,
    )



def build_remote_task_worker(settings: AppSettings, *, facade=None):
    """创建 SmartAccess 远程任务 worker。

    Args:
        settings: 应用配置。
        facade: 可选已有的运行时门面；为空时构建新实例。

    Returns:
        远程任务 worker。
    """
    from smartaccess.runtime.application.platform_event_uploader import (
        PlatformEventUploader,
    )
    from smartaccess.runtime.application.remote_task_worker import RemoteTaskWorker

    if facade is None:
        facade = build_runtime_facade(settings)
    return RemoteTaskWorker(
        device_id=settings.device_id or str(settings.workspace_dir),
        facade=facade,
        uploader=PlatformEventUploader(facade.providers()["platform"]),
    )


def _run_mq_consumer(settings: AppSettings, worker, device_id: str) -> None:
    """连接 RabbitMQ 并阻塞消费远程任务消息。

    Args:
        settings: 应用配置。
        worker: 远程任务 worker。
        device_id: 当前设备 ID。
    """
    logger = get_logger()
    credentials = pika.PlainCredentials(
        settings.rabbitmq_username,
        settings.rabbitmq_password,
    )
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            credentials=credentials,
        )
    )
    channel = connection.channel()
    exchange = "smartaccess.commands"
    queue_name = f"smartaccess.device.{device_id}.commands"
    routing_key = f"device.{device_id}.run.requested"
    channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=routing_key)
    channel.basic_qos(prefetch_count=1)

    def _on_message(ch, method, properties, body) -> None:
        """处理 RabbitMQ 下发的 SmartAccess 任务消息。"""
        try:
            result = worker.handle_body(body)
            logger.info("SmartAccess 远程任务处理完成: result=%s", result)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError:
            logger.exception("SmartAccess 远程任务消息不是合法 JSON，已丢弃")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception:  # noqa: BLE001 - 防止消费循环退出
            logger.exception("SmartAccess 远程任务处理失败，消息不重入队")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
    logger.info(
        "SmartAccess 远程任务监听中: queue=%s routing_key=%s",
        queue_name,
        routing_key,
    )
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("SmartAccess worker 收到停止信号")
    except Exception:  # noqa: BLE001 - pika 连接异常
        logger.exception("SmartAccess 远程任务监听连接异常")
    finally:
        if connection.is_open:
            connection.close()


def start_remote_task_listener(settings: AppSettings, *, facade=None) -> None:
    """在后台线程启动 SmartAccess 远程任务监听。

    复用已有 facade（通常来自桌面端进程），不创建新的 provider 实例。
    保证窗口激活、坐标计算与桌面端手动执行完全一致。

    Args:
        settings: 应用配置。
        facade: 已有的运行时门面；为空时构建新实例。
    """
    import threading

    worker = build_remote_task_worker(settings, facade=facade)
    device_id = settings.device_id or str(settings.workspace_dir)
    logger = get_logger()
    logger.info(
        "SmartAccess 远程任务监听启动: device_id=%s, rabbitmq_enabled=%s",
        device_id,
        settings.rabbitmq_enabled,
    )
    if not settings.rabbitmq_enabled:
        logger.warning("RabbitMQ 未启用，跳过远程任务监听")
        return

    thread = threading.Thread(
        target=_run_mq_consumer,
        args=(settings, worker, device_id),
        name="smartaccess-mq-listener",
        daemon=True,
    )
    thread.start()
    logger.info("SmartAccess 远程任务监听线程已启动")


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

    from smartaccess.runtime.api.edge import create_edge_app

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

    ocr_mode = settings.ocr_mode.lower().strip()
    vision_provider = settings.vision_provider.lower().strip()
    if ocr_mode == "local" or vision_provider == "local":
        try:
            return LocalVisionProvider(workspace_dir=settings.workspace_dir)
        except Exception:  # noqa: BLE001 - 可选 OCR 依赖缺失时回退 stub
            get_logger().exception("本地视觉初始化失败，已回退 Stub")
    if ocr_mode in REMOTE_OCR_MODES or vision_provider == "api":
        try:
            return ApiVisionProvider(
                api_url=settings.ocr_api_url,
                ocr_mode=settings.ocr_mode,
                workspace_dir=settings.workspace_dir,
            )
        except Exception:  # noqa: BLE001 - API 不可用时回退 stub
            get_logger().exception("API 视觉初始化失败，已回退 Stub")
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


def _build_text_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """装配文字 LLM 生成器，用于 AI 生成工作流。

    Args:
        settings: 应用配置。

    Returns:
        文字 LLM 生成器；provider=template 或未配 API Key 时返回 None。
    """

    provider = settings.ai_text_provider.lower().strip()
    if provider == "template":
        return None
    if not settings.ai_text_api_key:
        get_logger().warning(
            "Text AI provider=%s 未配置 API Key，工作流 AI 生成未启用", provider
        )
        return None
    return SmartAccessAiGenerator(
        api_key=settings.ai_text_api_key,
        base_url=settings.ai_text_base_url,
        model=settings.ai_text_model,
        provider=provider,
        timeout_seconds=settings.ai_text_timeout_seconds,
        user_agent=settings.ai_user_agent,
    )


def _build_vision_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """装配多模态生成器，用于 AI 辅助接入。

    Args:
        settings: 应用配置。

    Returns:
        多模态生成器；provider=template 或未配 API Key 时返回 None。
    """

    provider = settings.ai_vision_provider.lower().strip()
    if provider == "template":
        return None
    if not settings.ai_vision_api_key:
        get_logger().warning(
            "Vision AI provider=%s 未配置 API Key，AI 辅助接入未启用", provider
        )
        return None
    return SmartAccessAiGenerator(
        api_key=settings.ai_vision_api_key,
        base_url=settings.ai_vision_base_url,
        model=settings.ai_vision_model,
        provider=provider,
        timeout_seconds=settings.ai_vision_timeout_seconds,
        user_agent=settings.ai_user_agent,
    )
