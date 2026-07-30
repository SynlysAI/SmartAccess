"""运行会话服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import uuid
from typing import Any

import yaml

from smartaccess.runtime.application.ports import ArtifactStore
from smartaccess.runtime.domain.run_session import RunSession, RunStep
from smartaccess.shared.contracts.run_trace import RunTraceRecord
from smartaccess.shared.contracts.workflow import WorkflowIncrementRule
from smartaccess.shared.events.bus import EventBus
from smartaccess.shared.events.runtime import RuntimeEventName

TRACE_FILE = "run_trace.jsonl"


class IncrementCounterError(RuntimeError):
    """Raised when an increment counter cannot be acquired or advanced."""


@dataclass(frozen=True, slots=True)
class IncrementReservation:
    """A run-scoped counter reservation."""

    workflow_id: str
    sequence_key: str
    value: int
    rendered: str
    next_value: int


class IncrementCounterService:
    """Persist and reserve workflow-level increment counters."""

    def __init__(self, workspace_dir: Path) -> None:
        self._path = Path(workspace_dir) / "state" / "increment_counters.yaml"
        self._reservations: dict[tuple[str, str], str] = {}

    def preview_next(self, workflow_id: str, rule: WorkflowIncrementRule) -> int:
        """Return the next value that would be used by a workflow rule."""

        state = self._load_state()
        record = self._record(state, workflow_id, rule.sequence_key)
        return int(record.get("next_value", rule.start))

    def reserve(
        self,
        *,
        workflow_id: str,
        sequence_key: str,
        session_id: str,
    ) -> None:
        """Reserve a counter for a running session."""

        key = (workflow_id, sequence_key)
        owner = self._reservations.get(key)
        if owner and owner != session_id:
            raise IncrementCounterError(
                f"increment counter {workflow_id}/{sequence_key} is in use by {owner}"
            )
        self._reservations[key] = session_id

    def render(
        self,
        *,
        workflow_id: str,
        session_id: str,
        rule: WorkflowIncrementRule,
        context: dict[str, str],
    ) -> IncrementReservation:
        """Render the current value for a reserved counter."""

        self.reserve(
            workflow_id=workflow_id,
            sequence_key=rule.sequence_key,
            session_id=session_id,
        )
        state = self._load_state()
        record = self._record(state, workflow_id, rule.sequence_key)
        value = int(record.get("next_value", rule.start))
        next_value = self._next_value(value, rule)
        rendered = rule.pattern.format(
            **context,
            date=datetime.now().strftime(rule.date_format),
            counter=value,
        )
        return IncrementReservation(
            workflow_id=workflow_id,
            sequence_key=rule.sequence_key,
            value=value,
            rendered=rendered,
            next_value=next_value,
        )

    def commit(self, session_id: str, reservations: list[IncrementReservation]) -> None:
        """Advance used counters once after a successful run."""

        if not reservations:
            return
        state = self._load_state()
        for reservation in reservations:
            key = (reservation.workflow_id, reservation.sequence_key)
            owner = self._reservations.get(key)
            if owner and owner != session_id:
                raise IncrementCounterError(
                    f"increment counter {reservation.workflow_id}/{reservation.sequence_key} "
                    f"is in use by {owner}"
                )
            workflow_records = state.setdefault(reservation.workflow_id, {})
            workflow_records[reservation.sequence_key] = {
                "next_value": reservation.next_value,
                "last_value": reservation.value,
                "last_session": session_id,
                "last_rendered": reservation.rendered,
            }
        self._save_state(state)
        self.release(session_id)

    def release(self, session_id: str) -> None:
        """Release all counters held by a session."""

        for key, owner in list(self._reservations.items()):
            if owner == session_id:
                self._reservations.pop(key, None)

    def _next_value(self, value: int, rule: WorkflowIncrementRule) -> int:
        if rule.max_value is not None and value >= rule.max_value:
            if rule.cycle:
                return int(rule.min_value if rule.min_value is not None else rule.start)
            raise IncrementCounterError(
                f"increment counter {rule.sequence_key} reached max_value={rule.max_value}"
            )
        return value + 1

    def _record(
        self,
        state: dict[str, dict[str, Any]],
        workflow_id: str,
        sequence_key: str,
    ) -> dict[str, Any]:
        workflow_records = state.setdefault(workflow_id, {})
        return dict(workflow_records.get(sequence_key) or {})

    def _load_state(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _save_state(self, state: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            yaml.safe_dump(state, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )


class RunSessionService:
    """创建运行会话、记录轨迹并发布运行事件。"""

    def __init__(self, *, artifact_store: ArtifactStore, event_bus: EventBus) -> None:
        """初始化运行会话服务。"""

        self._artifacts = artifact_store
        self._event_bus = event_bus
        self._sessions: dict[str, RunSession] = {}
        self._traces: dict[str, list[RunTraceRecord]] = {}
        self._stop_requests: dict[str, str] = {}
        self._order: list[str] = []

    def create_session(
        self,
        workflow_id: str,
        *,
        steps: list[RunStep] | None = None,
        device_id: str | None = None,
        author: str | None = None,
        workflow_name: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
    ) -> RunSession:
        """创建运行会话。"""

        session_id = f"run_{uuid.uuid4().hex[:12]}"
        session = RunSession(
            session_id=session_id,
            workflow_id=workflow_id,
            device_id=device_id,
            author=author,
            workflow_name=workflow_name or workflow_id,
            template_id=template_id,
            template_version=template_version,
            steps=list(steps or []),
        )
        self._sessions[session_id] = session
        self._traces[session_id] = []
        self._order.append(session_id)
        self.emit_event(
            session,
            RuntimeEventName.RUN_CREATED,
            workflow_id=workflow_id,
            device_id=session.device_id,
            author=session.author,
            workflow_name=session.workflow_name,
        )
        return session

    def emit_event(
        self,
        session: RunSession,
        event: RuntimeEventName,
        **payload: Any,
    ) -> None:
        """推进会话状态并发布事件。"""

        session.apply(event)
        payload.setdefault("workflow_id", session.workflow_id)
        payload.setdefault("device_id", session.device_id)
        payload.setdefault("author", session.author)
        payload.setdefault("workflow_name", session.workflow_name or session.workflow_id)
        self._event_bus.emit(event, session_id=session.session_id, **payload)

    def append_trace(self, record: RunTraceRecord) -> str:
        """追加运行轨迹记录。"""

        self._traces.setdefault(record.session_id, []).append(record)
        return self._artifacts.append_jsonl(
            record.session_id,
            TRACE_FILE,
            record.model_dump_json(exclude_none=True),
        )

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        """保存运行截图。"""

        return self._artifacts.save_screenshot(session_id, name, data)

    def get_session(self, session_id: str) -> RunSession | None:
        """读取运行会话。"""

        return self._sessions.get(session_id)

    def get_trace(self, session_id: str) -> list[RunTraceRecord]:
        """读取运行轨迹。"""

        return list(self._traces.get(session_id, []))

    def request_stop(self, session_id: str, *, reason: str = "stopped by user") -> bool:
        """请求停止运行会话。"""

        session = self.get_session(session_id)
        if session is None:
            return False
        self._stop_requests[session_id] = reason
        self.emit_event(
            session,
            RuntimeEventName.RUN_STOPPING,
            detail=reason,
            requested_by="user",
        )
        return True

    def cancel(self, session_id: str, *, reason: str = "cancelled") -> bool:
        """标记运行会话已取消。"""

        session = self.get_session(session_id)
        if session is None:
            return False
        self.emit_event(session, RuntimeEventName.RUN_CANCELLED, detail=reason)
        return True

    def stop_requested(self, session_id: str) -> bool:
        """返回是否请求停止。"""

        return session_id in self._stop_requests

    def stop_reason(self, session_id: str) -> str:
        """返回停止原因。"""

        return self._stop_requests.get(session_id, "stopped by user")

    def list_sessions(self) -> list[RunSession]:
        """列出运行会话。"""

        return [self._sessions[session_id] for session_id in self._order]

    def recent(self, limit: int = 5) -> list[RunSession]:
        """返回最近运行会话。"""

        return [self._sessions[session_id] for session_id in self._order[-limit:]][::-1]
