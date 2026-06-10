"""RunSessionService: own run sessions, their trace, and event emission.

Creates sessions, records ``run_trace.jsonl`` events through the
:class:`ArtifactStore` port, and publishes runtime events to the bus so the
desktop monitoring page and platform sync can react live.
"""

from __future__ import annotations

import uuid
from typing import Any

from smartaccess.runtime.application.ports import ArtifactStore
from smartaccess.runtime.domain.run_session import RunSession, RunStep
from smartaccess.shared.contracts.run_trace import RunTraceRecord
from smartaccess.shared.events import EventBus, RuntimeEventName

_TRACE_FILE = "run_trace.jsonl"


class RunSessionService:
    """Creates run sessions and records their trace + events."""

    def __init__(self, *, artifact_store: ArtifactStore, event_bus: EventBus) -> None:
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
        template_id: str | None = None,
        template_version: str | None = None,
    ) -> RunSession:
        session_id = f"run_{uuid.uuid4().hex[:12]}"
        session = RunSession(
            session_id=session_id,
            workflow_id=workflow_id,
            template_id=template_id,
            template_version=template_version,
            steps=list(steps or []),
        )
        self._sessions[session_id] = session
        self._traces[session_id] = []
        self._order.append(session_id)
        self.emit_event(session, RuntimeEventName.RUN_CREATED, workflow_id=workflow_id)
        return session

    def emit_event(
        self, session: RunSession, event: RuntimeEventName, **payload: Any
    ) -> None:
        """Advance the session state machine and publish the event."""

        session.apply(event)
        self._event_bus.emit(event, session_id=session.session_id, **payload)

    def append_trace(self, record: RunTraceRecord) -> str:
        """Store and persist a single run-trace record."""

        self._traces.setdefault(record.session_id, []).append(record)
        return self._artifacts.append_jsonl(
            record.session_id, _TRACE_FILE, record.model_dump_json(exclude_none=True)
        )

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        return self._artifacts.save_screenshot(session_id, name, data)

    def get_session(self, session_id: str) -> RunSession | None:
        return self._sessions.get(session_id)

    def get_trace(self, session_id: str) -> list[RunTraceRecord]:
        return list(self._traces.get(session_id, []))

    def request_stop(self, session_id: str, *, reason: str = "stopped by user") -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        self._stop_requests[session_id] = reason
        self.emit_event(session, RuntimeEventName.RUN_FAILED, detail=reason, requested_by="user")
        return True

    def stop_requested(self, session_id: str) -> bool:
        return session_id in self._stop_requests

    def stop_reason(self, session_id: str) -> str:
        return self._stop_requests.get(session_id, "stopped by user")

    def list_sessions(self) -> list[RunSession]:
        return [self._sessions[sid] for sid in self._order]

    def recent(self, limit: int = 5) -> list[RunSession]:
        return [self._sessions[sid] for sid in self._order[-limit:]][::-1]
