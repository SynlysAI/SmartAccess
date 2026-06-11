"""Run monitoring view model: drives a run and streams its events to the UI."""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal

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
        self._audit_rows: dict[str, dict] = {}
        relay.event_received.connect(self._on_event)

    def start(self, workflow: WorkflowContract) -> RunSession:
        steps_data = [
            {
                "id": step.id,
                "action": step.action,
                "anchor_id": step.anchor_id or "",
                "value": step.value or "",
            }
            for step in workflow.steps
        ]
        self.clear_display.emit()
        self._audit_rows = {
            step["id"]: {
                "step_id": step["id"],
                "action": step["action"],
                "anchor_id": step["anchor_id"],
                "value": step["value"],
                "status": "pending",
                "wait_strategy": {"type": "fixed_wait"},
                "match_mode": "none",
            }
            for step in steps_data
        }
        self.run_state.emit("running")
        self.steps_reset.emit(steps_data)
        self.log_line.emit("Run requested; creating background session.")
        session = self._facade.start_run(workflow=workflow, background=True)
        self._session_id = session.session_id
        self._attach_reference_paths(workflow, session.session_id)
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

        if step_id:
            self._update_audit_row(name, payload)
            self.audit.emit(self._format_audit_html())

        if name == RuntimeEventName.RUN_STEP_OBSERVED:
            self.reading.emit(self._format_observation_html(payload))
            if payload.get("screenshot_path"):
                shot_link = self._path_link(str(payload["screenshot_path"]))
                self.shot.emit(
                    f"Latest screenshot saved to:<br>{shot_link}"
                )

        if name in (
            RuntimeEventName.RUN_RECOVERED,
            RuntimeEventName.RUN_BLOCKED,
            RuntimeEventName.RUN_FAILED,
        ):
            if not step_id:
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

    def _update_audit_row(self, name: RuntimeEventName, payload: dict) -> None:
        step_id = str(payload.get("step_id") or "")
        if not step_id:
            return
        row = self._audit_rows.setdefault(step_id, {"step_id": step_id})
        if name == RuntimeEventName.RUN_STEP_STARTED:
            row.update(
                {
                    "status": "running",
                    "action": payload.get("action"),
                    "anchor_id": payload.get("anchor_id"),
                    "value": payload.get("value"),
                    "requires_confirmation": payload.get("requires_confirmation"),
                    "expected_text": payload.get("expected_text"),
                    "match_mode": payload.get("match_mode") or "none",
                    "wait_seconds": payload.get("wait_seconds"),
                    "timeout_seconds": payload.get("timeout_seconds"),
                }
            )
        elif name == RuntimeEventName.RUN_STEP_OBSERVED:
            row.update(
                {
                    "status": "observed",
                    "expected_text": payload.get("expected_text"),
                    "actual_text": payload.get("actual_text"),
                    "match_mode": payload.get("match_mode") or "none",
                    "matched": payload.get("matched"),
                    "attempts": payload.get("attempts"),
                    "elapsed_seconds": payload.get("elapsed_seconds"),
                    "wait_strategy": payload.get("wait_strategy") or {},
                    "screenshot_path": payload.get("screenshot_path"),
                    "readings": payload.get("readings") or [],
                }
            )
        elif name == RuntimeEventName.RUN_STEP_SUCCEEDED:
            row["status"] = "succeeded"
        elif name == RuntimeEventName.RUN_BLOCKED:
            row["status"] = "blocked"
            row["error"] = payload.get("reason")
        elif name == RuntimeEventName.RUN_FAILED:
            row["status"] = "failed"
            row["error"] = payload.get("detail")

    def _format_audit_html(self) -> str:
        if not self._audit_rows:
            return "暂无步骤审计。"
        rows = ["<div style='line-height:160%;'>"]
        for row in self._audit_rows.values():
            rows.append(self._format_audit_card(row))
        rows.append("</div>")
        return "".join(rows)

    @staticmethod
    def _format_audit_card(row: dict) -> str:
        status = html.escape(str(row.get("status") or "pending"))
        step_id = html.escape(str(row.get("step_id") or "-"))
        action = html.escape(str(row.get("action") or "-"))
        anchor = html.escape(str(row.get("anchor_id") or "-"))
        value = html.escape(str(row.get("value") or "-"))
        wait_strategy = row.get("wait_strategy") or {}
        strategy_type = wait_strategy.get("type") or ("ocr_poll" if row.get("match_mode") != "none" else "fixed_wait")
        needs_check = row.get("match_mode") not in (None, "", "none")
        standard = "无需观测校验"
        if needs_check:
            standard = f"{row.get('match_mode')} / {row.get('expected_text') or '非空文本'}"
        actual = html.escape(str(row.get("actual_text") or "-"))
        matched = row.get("matched")
        if matched is True:
            match_text = "通过"
        elif matched is False:
            match_text = "未命中"
        else:
            match_text = "不适用"
        attempts = html.escape(str(row.get("attempts") or "-"))
        elapsed = row.get("elapsed_seconds")
        elapsed_text = f"{float(elapsed):.2f}s" if isinstance(elapsed, (int, float)) else "-"
        shot = MonitoringViewModel._path_link(str(row.get("screenshot_path") or "-"))
        refs = MonitoringViewModel._format_reference_links(row)
        error = html.escape(str(row.get("error") or "-"))
        return (
            "<div style='margin:8px 0;padding:10px 12px;border:1px solid #39414f;border-radius:8px;'>"
            f"<div><b>{step_id}</b> · {status}</div>"
            f"<div>动作：{action} · 锚点：{anchor} · 值：{value}</div>"
            f"<div>观测策略：{html.escape(str(strategy_type))} · 校验：{html.escape(standard)}</div>"
            f"<div>实测值：{actual} · 匹配：{html.escape(match_text)} · 尝试：{attempts} · 耗时：{html.escape(elapsed_text)}</div>"
            f"<div>截图：{shot}</div>"
            f"{refs}"
            f"<div>错误：{error}</div>"
            "</div>"
        )

    def _attach_reference_paths(self, workflow: WorkflowContract, session_id: str) -> None:
        workspace = Path(self._facade.workspace_dir())
        workflow_id = workflow.metadata.workflow_id
        anchor_profile = workflow.metadata.anchor_profile
        refs = {
            "trace_path": str(workspace / "runs" / session_id / "run_trace.jsonl"),
            "workflow_path": str(workspace / "workflows" / workflow_id / "draft.yaml"),
            "anchors_path": str(workspace / "anchors" / anchor_profile / "anchors.yaml"),
        }
        for row in self._audit_rows.values():
            row.update(refs)

    @staticmethod
    def _path_link(path_text: str) -> str:
        """Render a filesystem path as visible text plus a clickable file link."""

        raw = str(path_text or "").strip()
        if not raw or raw == "-":
            return "<code>-</code>"
        normalized = raw.replace("\\", "/")
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        href = QUrl.fromLocalFile(str(path.resolve())).toString()
        visible = html.escape(normalized)
        return f"<a href='{html.escape(href, quote=True)}'><code>{visible}</code></a>"

    @staticmethod
    def _format_reference_links(row: dict) -> str:
        links: list[str] = []
        for label, key in (
            ("trace", "trace_path"),
            ("workflow", "workflow_path"),
            ("anchors", "anchors_path"),
        ):
            value = row.get(key)
            if value:
                links.append(f"{html.escape(label)}={MonitoringViewModel._path_link(str(value))}")
        if not links:
            return ""
        return f"<div>引用：{' · '.join(links)}</div>"
