"""Run monitoring view model: drives a run and streams its events to the UI."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess.runtime.domain.run_session import RunSession
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events import RuntimeEvent, RuntimeEventName

from .base import EventRelay, ViewModel

_STEP_STATUS = {
    RuntimeEventName.RUN_STEP_STARTED: "running",
    RuntimeEventName.RUN_STEP_OBSERVED: "observed",
    RuntimeEventName.RUN_STEP_SUCCEEDED: "succeeded",
}


class MonitoringViewModel(ViewModel):
    steps_reset = pyqtSignal(list)
    step_changed = pyqtSignal(str, str)
    log_line = pyqtSignal(str)
    run_state = pyqtSignal(str)
    reading = pyqtSignal(str)
    audit = pyqtSignal(str)

    def __init__(self, facade, relay: EventRelay, parent=None) -> None:
        super().__init__(facade, parent)
        self._relay = relay
        self._session_id: str | None = None
        relay.event_received.connect(self._on_event)

    def start(self, workflow: WorkflowContract) -> RunSession:
        self.steps_reset.emit([s.id for s in workflow.steps])
        session = self._facade.start_run(workflow=workflow, background=True)
        self._session_id = session.session_id
        self.log_line.emit(f"启动运行 session={session.session_id}")
        self.audit.emit(f"会话 {session.session_id}\n模板 {session.template_id or '-'}@{session.template_version or '-'}")
        return session

    def _on_event(self, event: RuntimeEvent) -> None:
        if self._session_id and event.session_id and event.session_id != self._session_id:
            return

        name = event.name
        payload = event.payload
        stamp = event.timestamp.strftime("%H:%M:%S")
        self.log_line.emit(f"{stamp}  {name.value}  {self._format_payload(payload)}")

        step_id = payload.get("step_id")
        if name in _STEP_STATUS and step_id:
            self.step_changed.emit(step_id, _STEP_STATUS[name])
        elif name == RuntimeEventName.RUN_BLOCKED and step_id:
            self.step_changed.emit(step_id, "blocked")
        if name == RuntimeEventName.RUN_STEP_OBSERVED and "min_confidence" in payload:
            self.reading.emit(f"最低置信度 {payload['min_confidence']:.2f}")
        if name in (RuntimeEventName.RUN_RECOVERED, RuntimeEventName.RUN_BLOCKED, RuntimeEventName.RUN_FAILED):
            self.audit.emit(f"{name.value}\n{self._format_payload(payload)}")
        if name in (
            RuntimeEventName.RUN_READY,
            RuntimeEventName.RUN_COMPLETED,
            RuntimeEventName.RUN_FAILED,
        ):
            self.run_state.emit(name.value)

    @staticmethod
    def _format_payload(payload: dict) -> str:
        if not payload:
            return ""
        return ", ".join(f"{k}={v}" for k, v in payload.items())
