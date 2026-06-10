"""Run monitoring view model: drives a run and streams its events to the UI."""

from __future__ import annotations

import html

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
    steps_reset = pyqtSignal(object)  # list[dict[str, str]]
    step_changed = pyqtSignal(str, str, str)  # step_id, status, HH:MM:SS
    clear_display = pyqtSignal()
    log_line = pyqtSignal(str)
    run_state = pyqtSignal(str)
    reading = pyqtSignal(str)
    audit = pyqtSignal(str)
    shot = pyqtSignal(str)

    def __init__(self, facade, relay: EventRelay, parent=None) -> None:
        super().__init__(facade, parent)
        self._relay = relay
        self._session_id: str | None = None
        relay.event_received.connect(self._on_event)

    def start(self, workflow: WorkflowContract) -> RunSession:
        steps_data = [
            {"id": step.id, "action": step.action, "target": step.target or "", "value": step.value or ""}
            for step in workflow.steps
        ]
        self.clear_display.emit()
        self.run_state.emit("running")
        self.steps_reset.emit(steps_data)
        self.log_line.emit("Run requested; creating background session.")
        session = self._facade.start_run(workflow=workflow, background=True)
        self._session_id = session.session_id
        self.log_line.emit(f"Started session={session.session_id}")
        self.audit.emit(
            f"Session <b>{session.session_id}</b><br>"
            f"Template {session.template_id or '-'}@{session.template_version or '-'}"
        )
        return session

    def stop(self, *, cancel: bool = False) -> bool:
        if not self._session_id:
            self.log_line.emit("当前没有正在监控的运行会话。")
            return False
        action = "取消" if cancel else "停止"
        ok = self._facade.request_run_stop(
            self._session_id,
            reason=f"用户请求{action}运行；当前执行器会在下一次运行事件后停止展示。",
        )
        if ok:
            self.log_line.emit(f"已请求{action} session={self._session_id}")
            self.run_state.emit("stopping" if not cancel else "cancelling")
        else:
            self.log_line.emit(f"{action}失败：找不到当前运行会话。")
        return ok

    def _on_event(self, event: RuntimeEvent) -> None:
        if self._session_id and event.session_id and event.session_id != self._session_id:
            return

        name = event.name
        payload = event.payload
        stamp = event.timestamp.strftime("%H:%M:%S")
        self.log_line.emit(f"{stamp}  {name.value}  {self._format_payload(payload)}")

        step_id = payload.get("step_id")
        if name in _STEP_STATUS and step_id:
            self.step_changed.emit(step_id, _STEP_STATUS[name], stamp)
        elif name == RuntimeEventName.RUN_BLOCKED and step_id:
            self.step_changed.emit(step_id, "blocked", stamp)
        elif name == RuntimeEventName.RUN_FAILED and step_id:
            self.step_changed.emit(step_id, "failed", stamp)

        if name == RuntimeEventName.RUN_STEP_OBSERVED:
            self.reading.emit(self._format_observation_html(payload))
            if payload.get("screenshot_path"):
                self.shot.emit(
                    f"Latest screenshot saved to:<br><code>{html.escape(str(payload['screenshot_path']))}</code>"
                )

        if name in (
            RuntimeEventName.RUN_RECOVERED,
            RuntimeEventName.RUN_BLOCKED,
            RuntimeEventName.RUN_FAILED,
        ):
            self.audit.emit(f"{name.value}<br>{html.escape(self._format_payload(payload))}")
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
        return ", ".join(f"{key}={value}" for key, value in payload.items())

    @staticmethod
    def _format_observation_html(payload: dict) -> str:
        readings = payload.get("readings") or []
        if not readings:
            return "<span>No observation readings yet.</span>"

        lines = [
            f"<div><b>Sources</b>: {html.escape(', '.join(payload.get('sources') or ['-']))}</div>",
            f"<div><b>Min confidence</b>: {float(payload.get('min_confidence', 0.0)):.2f}</div>",
            "<div style='margin-top:6px;'><b>Readings</b></div>",
        ]
        for reading in readings:
            roi = html.escape(str(reading.get("roi", "-")))
            text = html.escape(str(reading.get("text", "")))
            confidence = float(reading.get("confidence", 0.0))
            detail = html.escape(str(reading.get("detail", "")))
            lines.append(
                "<div style='margin-top:4px;padding:6px 8px;border:1px solid #39414f;"
                "border-radius:8px;'>"
                f"<div><b>{roi}</b> · confidence {confidence:.2f}</div>"
                f"<div>text: {text or '-'}</div>"
                f"<div>detail: {detail or '-'}</div>"
                "</div>"
            )
        return "".join(lines)
