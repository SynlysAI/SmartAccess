"""桌面 UI 使用的粗粒度运行时门面。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from smartaccess.runtime.application.ports import (
    ArtifactStore,
    AutomationProvider,
    OcrReading,
    PlatformClient,
    VisionProvider,
    WindowInfo,
    InstrumentProfileDraftGenerator,
)
from smartaccess.runtime.application.anchor_service import AnchorService
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.migration_service import (
    MigrationReport,
    MigrationService,
)
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.run_session_service import RunSessionService
from smartaccess.runtime.application.template_service import (
    TemplateRecord,
    TemplateStats,
    TemplateService,
)
from smartaccess.runtime.application.workflow_service import (
    StandardizationResult,
    WorkflowService,
)
from smartaccess.runtime.application.workspace_service import (
    DashboardProjection,
    WorkspaceService,
)
from smartaccess.runtime.domain.run_session import RunSession, RunStep
from smartaccess.runtime.orchestration import Orchestrator
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.anchors import AnchorDefinition, AnchorsContract
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events.bus import EventBus, Subscriber
from smartaccess.shared.logging import get_logger


@dataclass(slots=True)
class RuntimeStatus:
    """运行时依赖状态摘要。"""

    workspace_dir: Path
    automation_provider: str
    vision_provider: str
    platform_provider: str
    ai_provider: str


class RuntimeFacade:
    """桌面层访问运行时能力的统一入口。"""

    def __init__(
        self,
        *,
        settings: AppSettings,
        event_bus: EventBus,
        automation: AutomationProvider,
        vision: VisionProvider,
        platform: PlatformClient,
        artifacts: ArtifactStore,
        anchors: AnchorService,
        workflows: WorkflowService,
        templates: TemplateService,
        workspace: WorkspaceService,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        platform_sync: PlatformSyncService,
        orchestrator: Orchestrator | None = None,
        migration: MigrationService | None = None,
        ai_generator: InstrumentProfileDraftGenerator | None = None,
    ) -> None:
        """初始化运行时门面。

        Args:
            settings: 应用配置。
            event_bus: 运行时事件总线。
            automation: 自动化适配器。
            vision: 视觉适配器。
            platform: 平台适配器。
            artifacts: 运行产物存储。
            anchors: 锚点服务。
            workflows: 工作流服务。
            templates: 模板服务。
            workspace: 工作区概览服务。
            run_sessions: 运行会话服务。
            incidents: 异常服务。
            platform_sync: 平台同步服务。
            orchestrator: 可选工作流编排器。
            migration: 可选旧工作区导入服务。
            ai_generator: 可选 AI 草稿生成器。
        """

        self._settings = settings
        self._event_bus = event_bus
        self._automation = automation
        self._vision = vision
        self._platform = platform
        self._artifacts = artifacts
        self._anchors = anchors
        self._workflows = workflows
        self._templates = templates
        self._workspace = workspace
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._platform_sync = platform_sync
        self._orchestrator = orchestrator
        self._migration = migration
        self._ai_generator = ai_generator
        self._logger = get_logger()

    def subscribe(self, callback: Subscriber):
        """订阅运行时事件。

        Args:
            callback: 事件回调。

        Returns:
            取消订阅函数。
        """

        return self._event_bus.subscribe(callback)

    def status(self) -> RuntimeStatus:
        """返回运行时状态摘要。"""

        return RuntimeStatus(
            workspace_dir=Path(self._settings.workspace_dir),
            automation_provider=self._settings.automation_provider,
            vision_provider=self._settings.vision_provider,
            platform_provider=self._settings.platform_provider,
            ai_provider=self._settings.ai_provider,
        )

    def workspace_dir(self) -> Path:
        """返回 工作区目录。"""

        return Path(self._settings.workspace_dir)

    def settings(self) -> AppSettings:
        """返回应用配置。"""

        return self._settings

    def discover_windows(self) -> list[WindowInfo]:
        """扫描可接入窗口。"""

        return self._automation.discover_windows()

    def capture_window(self, hwnd: int) -> bytes | None:
        """截取指定窗口。

        Args:
            hwnd: 窗口句柄。

        Returns:
            PNG 字节；失败时返回 None。
        """

        return self._automation.capture_window(hwnd)

    def capture_windows(self, hwnds: list[int]) -> bytes | None:
        """截取多个窗口的屏幕联合区域。

        Args:
            hwnds: 窗口句柄列表。

        Returns:
            PNG 字节；失败时返回 None。
        """

        method = getattr(self._automation, "capture_windows", None)
        if callable(method):
            return method(hwnds)
        if len(hwnds) == 1:
            return self._automation.capture_window(hwnds[0])
        return None

    def platform_health(self) -> bool:
        """返回平台连接是否可用。"""

        return self._platform.health()

    def dashboard(self) -> DashboardProjection:
        """返回运行概览投影。"""

        return self._workspace.dashboard()

    def list_instruments(self) -> list[AnchorsContract]:
        """列出设备锚点配置。"""

        return self._anchors.list_profiles()

    def get_instrument(self, device_id: str | None) -> AnchorsContract | None:
        """读取设备锚点配置。"""

        return self._anchors.get_profile(device_id)

    def save_instrument(self, profile: AnchorsContract) -> AnchorsContract:
        """保存设备锚点配置。"""

        self._anchors.save_profile(profile)
        return profile

    def create_calibration(
        self,
        *,
        device_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]],
        views: list[dict[str, Any]] | None = None,
        capture_width: int | None,
        capture_height: int | None,
        capture_origin_x: int | None = None,
        capture_origin_y: int | None = None,
        capture_mode: str = "window",
        capture_screen_origin_x: int | None = None,
        capture_screen_origin_y: int | None = None,
        capture_windows: list[dict[str, Any]] | None = None,
    ) -> AnchorsContract:
        """创建并保存设备校准配置。

        Args:
            device_id: 设备 ID。
            title_contains: 窗口标题包含文本。
            anchors: 锚点原始数据。
            capture_width: 校准截图宽度。
            capture_height: 校准截图高度。
            capture_origin_x: 兼容旧窗口模式的截图原点 X 偏移。
            capture_origin_y: 兼容旧窗口模式的截图原点 Y 偏移。
            capture_mode: 截图坐标模式。
            capture_screen_origin_x: 校准截图画布在屏幕上的左上角 X。
            capture_screen_origin_y: 校准截图画布在屏幕上的左上角 Y。
            capture_windows: 参与截图的窗口元数据。

        Returns:
            已保存的锚点配置。
        """

        return self._anchors.create_profile(
            profile_id=device_id,
            title_contains=title_contains,
            anchors=anchors,
            views=views,
            capture_width=capture_width,
            capture_height=capture_height,
            capture_origin_x=capture_origin_x,
            capture_origin_y=capture_origin_y,
            capture_mode=capture_mode,
            capture_screen_origin_x=capture_screen_origin_x,
            capture_screen_origin_y=capture_screen_origin_y,
            capture_windows=capture_windows,
        )

    def save_instrument_capture(
        self,
        device_id: str,
        data: bytes,
        *,
        view_id: str | None = None,
    ) -> Path:
        """保存设备校准截图。

        Args:
            device_id: 设备 ID。
            data: PNG 截图字节。

        Returns:
            保存后的截图路径。
        """

        return self._anchors.save_capture(device_id, data, view_id=view_id)

    def load_instrument_capture(
        self,
        device_id: str | None,
        *,
        view_id: str | None = None,
    ) -> bytes | None:
        """读取设备校准截图。

        Args:
            device_id: 设备 ID。

        Returns:
            PNG 截图字节；不存在时返回 None。
        """

        return self._anchors.load_capture(device_id, view_id=view_id)

    def delete_instrument_capture(
        self,
        device_id: str,
        *,
        view_id: str | None = None,
    ) -> None:
        """删除设备校准截图。

        Args:
            device_id: 设备 ID。
            view_id: 视图 ID；为空或 main 时删除主截图。
        """

        self._anchors.delete_capture(device_id, view_id=view_id)

    def preview_anchor_ocr(
        self,
        *,
        capture_data: bytes,
        anchor_payload: dict[str, Any],
    ) -> OcrReading:
        """对一张校准截图中的单个锚点执行一次 OCR 预览。"""

        anchor = AnchorDefinition.model_validate(anchor_payload)
        method = getattr(self._vision, "read_roi_text", None)
        if not callable(method):
            raise RuntimeError("当前视觉提供者不支持锚点 OCR 预览")
        return method(screenshot=capture_data, anchor=anchor, roi=None)

    def draft_instrument_from_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> AnchorsContract:
        """调用 AI 生成设备锚点草稿。

        Args:
            prompt: 用户描述。
            context: 生成上下文。

        Returns:
            锚点配置草稿。
        """

        if self._ai_generator is None:
            raise RuntimeError("AI 生成功能未配置")
        method = getattr(self._ai_generator, "draft_instrument_profile", None)
        if not callable(method):
            raise RuntimeError("当前 AI 生成器不支持设备接入")
        self._logger.info("AI 辅助接入: 生成锚点草稿中... prompt=%.100s", prompt)
        result = method(prompt, context)
        self._logger.info("AI 辅助接入: 锚点草稿生成完成 profile_id=%s, 锚点数=%d",
                          result.profile_id, len(result.anchors))
        return result

    def draft_workflow_from_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> WorkflowContract:
        """调用 AI 生成工作流草稿。

        Args:
            prompt: 用户描述。
            context: 生成上下文。

        Returns:
            工作流草稿。
        """

        return self._workflows.draft_from_prompt(prompt, context)

    def ai_reasoning(self) -> str:
        """返回最近一次 AI 生成摘要。"""

        if self._ai_generator is None:
            return ""
        return str(getattr(self._ai_generator, "last_reasoning", "") or "")

    def ai_label(self) -> str:
        """返回 AI 生成器标签。"""

        if self._ai_generator is None:
            return "未配置"
        label = getattr(self._ai_generator, "generator_label", None)
        return str(label()) if callable(label) else type(self._ai_generator).__name__

    def delete_instrument(self, device_id: str) -> None:
        """删除设备锚点配置。"""

        self._anchors.delete_profile(device_id)

    def list_workflows(self) -> list[WorkflowContract]:
        """列出工作流。"""

        return self._workflows.list_workflows()

    def get_workflow(self, workflow_id: str) -> WorkflowContract | None:
        """读取工作流。"""

        return self._workflows.get(workflow_id)

    def save_workflow(self, workflow: WorkflowContract) -> WorkflowContract:
        """保存工作流。"""

        return self._workflows.update(workflow)

    def delete_workflow(self, workflow_id: str) -> None:
        """删除工作流。"""

        self._workflows.delete_workflow(workflow_id)

    def standardize(self, workflow: WorkflowContract) -> StandardizationResult:
        """执行工作流标准化检查。"""

        return self._workflows.standardize_check(workflow)

    def list_templates(self) -> list[TemplateRecord]:
        """列出模板记录。"""

        return self._templates.list_all()

    def search_templates(
        self,
        query: str = "",
        status: str = "",
    ) -> list[TemplateRecord]:
        """搜索模板记录。

        Args:
            query: 关键字。
            status: 模板状态过滤。

        Returns:
            模板记录列表。
        """

        return self._templates.search_templates(query=query, status=status)

    def refresh_cloud_templates(self) -> TemplateStats:
        """刷新云端模板索引。"""

        return self._templates.refresh_cloud_index()

    def publish_template(self, workflow: WorkflowContract) -> TemplateRecord:
        """发布模板。"""

        return self._templates.publish(workflow)

    def delete_template_version(
        self,
        template_id: str,
        template_version: str,
        *,
        force: bool = False,
    ) -> TemplateRecord:
        """删除模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            force: 是否强制删除发布版本。

        Returns:
            已删除的模板记录。
        """

        return self._templates.delete_version(
            template_id,
            template_version,
            force=force,
        )

    def delete_template_version_cloud_first(
        self,
        template_id: str,
        template_version: str,
        *,
        force: bool = False,
    ) -> TemplateRecord:
        """先删云端再删本地模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            force: 是否强制删除发布版本。

        Returns:
            已删除的模板记录。
        """

        return self._templates.delete_version_cloud_first(
            template_id,
            template_version,
            force=force,
        )

    def update_template_version(
        self,
        template_id: str,
        template_version: str,
        *,
        anchor_profile: str | None = None,
    ) -> TemplateRecord:
        """更新模板版本元数据。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            anchor_profile: 新设备锚点配置 ID。

        Returns:
            更新后的模板记录。
        """

        return self._templates.update_version_metadata(
            template_id,
            template_version,
            anchor_profile=anchor_profile,
        )

    def rollback_template(
        self,
        template_id: str,
        template_version: str,
    ) -> TemplateRecord:
        """回滚到指定模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            回滚后的模板记录。
        """

        return self._templates.rollback(template_id, template_version)

    def fetch_template(
        self,
        template_id: str,
        template_version: str,
    ) -> WorkflowContract:
        """读取本地模板工作流。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            工作流契约。
        """

        return self._templates.fetch(template_id, template_version)

    def sync_platform_outbox(self):
        """同步平台 outbox。"""

        return self._platform_sync.sync()

    def import_legacy_workspace(
        self,
        legacy_workspace: str | Path = "workspace",
    ) -> MigrationReport:
        """导入旧工作区数据并刷新本地缓存。

        Args:
            legacy_workspace: 旧工作区目录。

        Returns:
            导入报告。
        """

        if self._migration is None:
            raise RuntimeError("旧工作区导入服务未配置")
        report = self._migration.import_legacy_workspace(legacy_workspace)
        self._anchors.load_all()
        self._workflows.load_all()
        self._templates.load_all()
        return report

    def set_confirm_handler(self, handler) -> None:
        """设置运行时人工确认回调。

        Args:
            handler: 人工确认回调；传入 None 时使用默认允许策略。
        """

        if self._orchestrator is not None:
            self._orchestrator.set_confirm_handler(handler)

    def start_run(
        self,
        workflow: WorkflowContract,
        *,
        background: bool = True,
    ) -> RunSession:
        """启动工作流运行。

        Args:
            workflow: 待运行工作流。
            background: 是否在后台线程运行。

        Returns:
            创建的运行会话。
        """

        if self._orchestrator is None:
            raise RuntimeError("运行编排器未配置")
        self._logger.info("启动工作流运行: workflow_id=%s, 步骤数=%d, 后台=%s",
                          workflow.metadata.workflow_id, len(workflow.steps), background)
        profile = self.get_instrument(workflow.metadata.anchor_profile)
        session = self._run_sessions.create_session(
            workflow.metadata.workflow_id,
            steps=[
                RunStep(step_id=step.id, action=step.action)
                for step in workflow.steps
            ],
            template_id=workflow.metadata.template_id,
            template_version=workflow.metadata.template_version,
        )

        def _run() -> None:
            """后台执行工作流。"""

            self._orchestrator.run(
                workflow=workflow,
                profile=profile,
                session=session,
            )

        if background:
            thread = threading.Thread(
                target=_run,
                name=f"smartaccess-run-{session.session_id}",
                daemon=True,
            )
            thread.start()
        else:
            _run()
        return session

    def request_run_stop(
        self,
        session_id: str,
        *,
        reason: str = "stopped by user",
    ) -> bool:
        """请求停止运行会话。

        Args:
            session_id: 运行会话 ID。
            reason: 停止原因。

        Returns:
            是否成功发出停止请求。
        """

        return self._run_sessions.request_stop(session_id, reason=reason)

    def list_sessions(self) -> list[RunSession]:
        """列出全部运行会话。"""

        return self._run_sessions.list_sessions()

    def recent_sessions(self, limit: int = 10) -> list[RunSession]:
        """返回最近运行会话。

        Args:
            limit: 最大返回数量。

        Returns:
            最近运行会话列表。
        """

        return self._run_sessions.recent(limit)

    def get_session(self, session_id: str) -> RunSession | None:
        """读取运行会话。"""

        return self._run_sessions.get_session(session_id)

    def get_trace(self, session_id: str):
        """读取运行轨迹。"""

        return self._run_sessions.get_trace(session_id)

    def providers(self) -> dict[str, Any]:
        """返回底层 provider 对象，供后续服务装配过渡使用。"""

        return {
            "automation": self._automation,
            "vision": self._vision,
            "platform": self._platform,
            "artifacts": self._artifacts,
            "event_bus": self._event_bus,
            "anchors": self._anchors,
            "workflows": self._workflows,
            "templates": self._templates,
            "workspace": self._workspace,
            "run_sessions": self._run_sessions,
            "incidents": self._incidents,
            "platform_sync": self._platform_sync,
            "orchestrator": self._orchestrator,
            "migration": self._migration,
            "ai_generator": self._ai_generator,
        }
