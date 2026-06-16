"""运行监控视图模型。"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal

from smartaccess.desktop.viewmodels.base import EventRelay, ViewModel
from smartaccess.desktop.widgets import rich_text
from smartaccess.runtime.domain.run_session import RunSession
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events.bus import RuntimeEvent


@dataclass(slots=True)
class MonitorLogEntry:
    """运行监控日志行。"""

    timestamp: str
    level: str
    message: str
    session_id: str | None = None
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowRunSummary:
    """运行监控页展示的工作流与绑定设备摘要。"""

    workflow_id: str
    lifecycle_state: str
    template_label: str
    anchor_profile: str
    device_found: bool
    status_text: str
    title_contains: str | None = None
    match_mode: str = "equals"
    process_name: str | None = None
    anchor_count: int = 0
    ocr_anchor_count: int = 0
    actions: list[str] | None = None


class MonitoringViewModel(ViewModel):
    """运行监控页和运行时门面之间的适配层。"""

    changed = pyqtSignal()
    event_received = pyqtSignal(object)

    def __init__(self, facade, parent=None) -> None:
        """初始化运行监控视图模型。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(facade, parent)
        self._relay = EventRelay(facade, self)
        self._relay.event_received.connect(self._on_event)
        self._logs: list[MonitorLogEntry] = []
        self._active_session_id: str | None = None

    def close(self) -> None:
        """释放事件订阅。"""

        self._relay.close()

    def list_workflows(self) -> list[WorkflowContract]:
        """列出可运行工作流。"""

        return self._facade.list_workflows()

    def list_sessions(self) -> list[RunSession]:
        """列出运行会话。"""

        return self._facade.recent_sessions(50)

    def start_run(self, workflow_id: str) -> RunSession:
        """启动指定工作流。

        Args:
            workflow_id: 工作流 ID。

        Returns:
            新建运行会话。
        """

        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        session = self._facade.start_run(workflow, background=True)
        self._active_session_id = session.session_id
        self.changed.emit()
        return session

    def stop_run(self, session_id: str | None = None) -> bool:
        """请求停止运行。

        Args:
            session_id: 运行会话 ID；为空时使用当前会话。

        Returns:
            是否成功发出停止请求。
        """

        target = session_id or self._active_session_id
        if not target:
            return False
        return self._facade.request_run_stop(target, reason="用户请求停止")

    def active_session(self) -> RunSession | None:
        """返回当前选中的运行会话。"""

        if self._active_session_id is None:
            sessions = self.list_sessions()
            return sessions[0] if sessions else None
        return self._facade.get_session(self._active_session_id)

    def set_active_session(self, session_id: str | None) -> None:
        """设置当前选中的运行会话。"""

        self._active_session_id = session_id
        self.changed.emit()

    def logs(self) -> list[MonitorLogEntry]:
        """返回监控日志。"""

        return list(self._logs)

    def workflow_summary(self, workflow_id: str | None) -> WorkflowRunSummary | None:
        """返回工作流及其绑定设备的运行摘要。"""

        if not workflow_id:
            return None
        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            return None
        metadata = workflow.metadata
        anchor_profile = str(metadata.anchor_profile or "")
        template_label = self._template_label(
            metadata.template_id,
            metadata.template_version,
        )
        profile = self._facade.get_instrument(anchor_profile)
        if profile is None:
            return WorkflowRunSummary(
                workflow_id=str(metadata.workflow_id),
                lifecycle_state=str(metadata.lifecycle_state),
                template_label=template_label,
                anchor_profile=anchor_profile,
                device_found=False,
                status_text="未找到绑定设备配置",
                actions=[],
            )
        ocr_count = sum(1 for anchor in profile.anchors if anchor.observe_region is not None)
        return WorkflowRunSummary(
            workflow_id=str(metadata.workflow_id),
            lifecycle_state=str(metadata.lifecycle_state),
            template_label=template_label,
            anchor_profile=anchor_profile,
            device_found=True,
            status_text="已绑定设备配置",
            title_contains=profile.window_signature.title_contains,
            match_mode=profile.window_signature.match_mode or "equals",
            process_name=profile.window_signature.process_name,
            anchor_count=len(profile.anchors),
            ocr_anchor_count=ocr_count,
            actions=profile.actions,
        )

    def clear_logs(self) -> None:
        """清空运行日志。"""

        self._logs.clear()
        self.changed.emit()

    def _on_event(self, event: RuntimeEvent) -> None:
        """处理运行时事件。"""

        if event.session_id:
            self._active_session_id = event.session_id
        self._logs.append(self._log_entry(event))
        self.event_received.emit(event)
        self.changed.emit()

    @staticmethod
    def _log_entry(event: RuntimeEvent) -> MonitorLogEntry:
        """把运行事件转换成日志行。"""

        payload = event.payload
        step_id = payload.get("step_id")
        detail = payload.get("detail") or payload.get("reason") or ""
        action = payload.get("action")
        message = str(event.name.value)
        if step_id:
            message = f"{message} / {step_id}"
        if action:
            message = f"{message} / {action}"
        if event.name.value in {"run.step.observed", "run.failed"} and _has_ocr_payload(payload):
            message = MonitoringViewModel._append_ocr_detail(message, payload)
        if detail:
            message = f"{message} / {detail}"
        level = "INFO"
        if event.name.value.endswith("failed"):
            level = "ERROR"
        elif "blocked" in event.name.value or "stopping" in event.name.value:
            level = "WARN"
        return MonitorLogEntry(
            timestamp=event.timestamp.astimezone().strftime("%H:%M:%S"),
            level=level,
            message=message,
            session_id=event.session_id,
            step_id=str(step_id) if step_id else None,
        )

    @staticmethod
    def _append_ocr_detail(message: str, payload: dict) -> str:
        """为 OCR 观测日志追加规则和识别结果。"""

        match_mode = str(payload.get("match_mode") or "none")
        rule = rich_text.ocr_rule(match_mode, payload.get("expected_text"))
        actual_text = payload.get("actual_text") or "-"
        return (
            f"{message} / OCR规则: {rule} / OCR实际: {actual_text} / "
            f"匹配: {payload.get('matched')} / 尝试: {payload.get('attempts')}"
        )

    @staticmethod
    def _template_label(template_id: str | None, template_version: str | None) -> str:
        """格式化模板版本标签。"""

        if template_id and template_version:
            return f"{template_id}@{template_version}"
        if template_id:
            return str(template_id)
        return "-"


def _has_ocr_payload(payload: dict) -> bool:
    """Return whether an event payload carries OCR debug fields."""

    return (
        payload.get("match_mode") not in (None, "none")
        or payload.get("expected_text") is not None
        or payload.get("actual_text") is not None
    )
