"""Orchestrator: the runtime decision center.

Drives a run session step by step: executor runs the action, observer reads
state, and on failure the incident/recovery path decides retry, rollback,
manual confirmation, or abort. Every step emits runtime events and writes a
``run_trace.jsonl`` record. Designed to run synchronously (tests) or inside a
background thread (desktop) — it only talks to ports and services, never to a
GUI or concrete provider (software-design §5.1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.ports import ActionOutcome
from smartaccess.runtime.application.run_session_service import RunSessionService
from smartaccess.runtime.domain.incident import IncidentType, RecoveryAction
from smartaccess.runtime.domain.run_session import RunSession, RunStep, RunStepStatus
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract
from smartaccess.shared.contracts.run_trace import (
    ActionPayload,
    ArtifactPayload,
    ObservationPayload,
    ResultPayload,
    RunTraceRecord,
)
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowStep
from smartaccess.shared.events import RuntimeEventName

from .executor import (
    AnchorMissingError,
    Executor,
    ExecutorError,
    SafetyViolationError,
    WindowMissingError,
)
from .observer import Observation, Observer
from .recovery import RecoveryEngine


@dataclass(slots=True)
class ConfirmRequest:
    """A request for human confirmation at a gate or high-risk recovery."""

    session_id: str
    step_id: str
    reason: str
    incident_type: str | None = None


ConfirmHandler = Callable[[ConfirmRequest], bool]


class Orchestrator:
    """Coordinates executor, observer, and recovery across a run session."""

    def __init__(
        self,
        *,
        executor: Executor,
        observer: Observer,
        recovery: RecoveryEngine,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        confirm_handler: ConfirmHandler | None = None,
        max_retries: int = 2,
    ) -> None:
        self._executor = executor
        self._observer = observer
        self._recovery = recovery
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._confirm: ConfirmHandler = confirm_handler or (lambda _request: True)
        self._max_retries = max_retries

    def run(
        self,
        *,
        workflow: WorkflowContract,
        profile: InstrumentProfileContract | None,
        session: RunSession,
    ) -> RunSession:
        rs = self._run_sessions
        self._executor.configure_profile(profile)
        safety = profile.safety_limits if profile else None
        title = profile.window_signature.title_contains if profile else None
        rois = list(workflow.roi_bindings.values())

        rs.emit_event(session, RuntimeEventName.RUN_READY)
        try:
            self._executor.ensure_window(title)
        except WindowMissingError as exc:
            if not self._handle_incident(
                session, "<window>", IncidentType.WINDOW_MISSING, str(exc)
            ):
                rs.emit_event(session, RuntimeEventName.RUN_FAILED, detail=str(exc))
                return session

        for step in workflow.steps:
            if not self._run_step(session, step, safety, rois):
                rs.emit_event(session, RuntimeEventName.RUN_FAILED, step_id=step.id)
                return session

        rs.emit_event(session, RuntimeEventName.RUN_COMPLETED)
        return session

    # ------------------------------------------------------------------ #
    def _run_step(self, session: RunSession, step: WorkflowStep, safety, rois) -> bool:
        rs = self._run_sessions
        self._set_step_status(session, step, RunStepStatus.RUNNING)
        rs.emit_event(
            session, RuntimeEventName.RUN_STEP_STARTED, step_id=step.id, action=step.action
        )

        # High-risk action gate: pause for human confirmation before acting.
        if self._executor.requires_confirm(step, safety):
            if not self._confirm_gate(session, step.id, f"步骤 {step.id} 为高风险动作，需人工确认"):
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False

        outcome = self._run_with_recovery(session, step, safety)
        if outcome is None:
            self._set_step_status(session, step, RunStepStatus.FAILED)
            return False

        observation = self._observer.observe(rois) if rois else Observation()
        if rois and self._observer.is_low_confidence(observation):
            if self._handle_incident(
                session,
                step.id,
                IncidentType.OCR_LOW_CONFIDENCE,
                f"低置信读数 {observation.min_confidence:.2f}",
            ):
                observation = self._observer.observe(rois)  # resample after recovery
        self._set_step_status(session, step, RunStepStatus.OBSERVED)
        rs.emit_event(
            session,
            RuntimeEventName.RUN_STEP_OBSERVED,
            step_id=step.id,
            min_confidence=observation.min_confidence,
        )

        self._record_trace(session, step, outcome, observation)
        self._set_step_status(session, step, RunStepStatus.SUCCEEDED)
        rs.emit_event(session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id)
        return True

    def _run_with_recovery(self, session: RunSession, step: WorkflowStep, safety):
        attempt = 0
        while True:
            try:
                return self._executor.run_step(step, safety)
            except SafetyViolationError as exc:
                # Safety violations are never silently bypassed.
                self._handle_incident(
                    session, step.id, IncidentType.SAFETY_LIMIT_VIOLATION, str(exc)
                )
                return None
            except (WindowMissingError, AnchorMissingError, ExecutorError) as exc:
                if not self._handle_incident(
                    session, step.id, self._classify(exc), str(exc)
                ):
                    return None
                attempt += 1
                if attempt > self._max_retries:
                    return None

    # ------------------------------------------------------------------ #
    def _confirm_gate(self, session: RunSession, step_id: str, reason: str) -> bool:
        rs = self._run_sessions
        rs.emit_event(session, RuntimeEventName.RUN_BLOCKED, step_id=step_id, reason=reason)
        ok = self._confirm(ConfirmRequest(session.session_id, step_id, reason))
        if ok:
            rs.emit_event(session, RuntimeEventName.RUN_RECOVERED, step_id=step_id)
        return ok

    def _handle_incident(
        self, session: RunSession, step_id: str, incident_type: IncidentType, detail: str
    ) -> bool:
        """Open an incident and decide recovery. Returns True if the run may continue."""

        incident = self._incidents.open(
            session_id=session.session_id,
            step_id=step_id,
            incident_type=incident_type,
            detail=detail,
        )
        action = self._recovery.decide(incident)

        if self._recovery.must_wait_for_human(incident):
            confirmed = self._confirm(
                ConfirmRequest(session.session_id, step_id, detail, incident_type.value)
            )
            if not confirmed:
                return False
            self._incidents.confirm(incident.incident_id)
            # Even an authorized confirm cannot turn an abort into a continue.
            return action != RecoveryAction.ABORT

        if action == RecoveryAction.ABORT:
            return False
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_RECOVERED,
            step_id=step_id,
            recovery=action.value,
        )
        return True

    @staticmethod
    def _classify(exc: Exception) -> IncidentType:
        if isinstance(exc, WindowMissingError):
            return IncidentType.WINDOW_MISSING
        if isinstance(exc, AnchorMissingError):
            return IncidentType.ANCHOR_MISSING
        return IncidentType.EXECUTOR_FAILED

    def _record_trace(
        self,
        session: RunSession,
        step: WorkflowStep,
        outcome: ActionOutcome,
        observation: Observation,
    ) -> None:
        record = RunTraceRecord(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            step_id=step.id,
            observation=ObservationPayload.model_validate(
                {
                    "readings": [
                        {"roi": r.roi, "text": r.text, "confidence": r.confidence}
                        for r in observation.readings
                    ],
                    "min_confidence": observation.min_confidence,
                }
            ),
            action=ActionPayload(type=step.action, target=step.target),
            result=ResultPayload(status="success", detail=outcome.detail or "ok"),
            artifacts=ArtifactPayload.model_validate(
                {"screenshot": outcome.screenshot_path}
                if outcome.screenshot_path
                else {}
            ),
        )
        self._run_sessions.append_trace(record)

    @staticmethod
    def _set_step_status(session: RunSession, step: WorkflowStep, status: RunStepStatus) -> None:
        for existing in session.steps:
            if existing.step_id == step.id:
                existing.status = status
                return
        session.steps.append(RunStep(step_id=step.id, action=step.action, status=status))
