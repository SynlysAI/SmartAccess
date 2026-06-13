"""运行监控视图模型。"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal

from smartaccess_v2.desktop.viewmodels.base import EventRelay, ViewModel
from smartaccess_v2.runtime.domain.run_session import RunSession
from smartaccess_v2.shared.contracts.workflow import WorkflowContract
from smartaccess_v2.shared.events.bus import RuntimeEvent


@dataclass(slots=True)
class MonitorLogEntry:
    """运行监控日志行。"""

    timestamp: str
    level: str
    message: str
    session_id: str | None = None
    step_id: str | None = None


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
