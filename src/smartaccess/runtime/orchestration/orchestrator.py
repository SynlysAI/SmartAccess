"""Orchestrator: the runtime decision center.

Drives a run session step by step: executor runs the action, observer reads
state, and on failure the incident/recovery path decides retry, rollback,
manual confirmation, or abort. Every step emits runtime events and writes a
``run_trace.jsonl`` record.
"""

from __future__ import annotations

import time
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
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowStep,
    normalize_condition,
)
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
        run_sessions = self._run_sessions
        self._executor.configure_profile(profile)
        safety = profile.safety_limits if profile else None
        title = profile.window_signature.title_contains if profile else None
        bindings = workflow.roi_bindings

        try:
            run_sessions.emit_event(session, RuntimeEventName.RUN_READY)
            self._executor.ensure_window(title)
        except WindowMissingError as exc:
            if not self._handle_incident(
                session, "<window>", IncidentType.WINDOW_MISSING, str(exc)
            ):
                run_sessions.emit_event(session, RuntimeEventName.RUN_FAILED, detail=str(exc))
                return session
        except Exception as exc:  # noqa: BLE001
            return self._fail_run(session, detail=f"Window bootstrap failed: {exc}")

        try:
            for step in workflow.steps:
                if run_sessions.stop_requested(session.session_id):
                    run_sessions.emit_event(
                        session,
                        RuntimeEventName.RUN_FAILED,
                        detail=run_sessions.stop_reason(session.session_id),
                    )
                    return session
                if not self._run_step(session, step, safety, profile, bindings):
                    run_sessions.emit_event(session, RuntimeEventName.RUN_FAILED, step_id=step.id)
                    return session

            run_sessions.emit_event(session, RuntimeEventName.RUN_COMPLETED)
            return session
        except Exception as exc:  # noqa: BLE001
            current_step = next(
                (existing for existing in session.steps if existing.status == RunStepStatus.RUNNING),
                None,
            )
            return self._fail_run(
                session,
                step_id=current_step.step_id if current_step else None,
                detail=f"Unhandled runtime error: {exc}",
            )

    def _run_step(
        self,
        session: RunSession,
        step: WorkflowStep,
        safety,
        profile: InstrumentProfileContract | None,
        bindings: dict[str, str],
    ) -> bool:
        run_sessions = self._run_sessions
        self._set_step_status(session, step, RunStepStatus.RUNNING)
        run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_STEP_STARTED,
            step_id=step.id,
            action=step.action,
        )

        if self._executor.requires_confirm(step, safety):
            if not self._confirm_gate(
                session,
                step.id,
                f"Step {step.id} requires manual confirmation before execution.",
            ):
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False

        if step.action in {"wait_until", "screenshot_check"}:
            return self._run_observation_action(session, step, profile, bindings)

        outcome = self._run_with_recovery(session, step, safety)
        if outcome is None:
            self._set_step_status(session, step, RunStepStatus.FAILED)
            return False

        observation_sources = self._step_observation_sources(step, bindings)
        observation = Observation()
        screenshot_path = None
        if observation_sources:
            observation, screenshot_path = self._observe_sources(
                session, step, profile, observation_sources
            )
            if self._observer.is_low_confidence(observation):
                if not self._handle_incident(
                    session,
                    step.id,
                    IncidentType.OCR_LOW_CONFIDENCE,
                    f"Low-confidence observation: {observation.min_confidence:.2f}",
                ):
                    self._set_step_status(session, step, RunStepStatus.FAILED)
                    return False
                observation, screenshot_path = self._observe_sources(
                    session, step, profile, observation_sources
                )

        self._set_step_status(session, step, RunStepStatus.OBSERVED)
        self._emit_observation_event(
            session,
            step,
            observation,
            observation_sources,
            screenshot_path=screenshot_path,
        )

        condition = normalize_condition(step.condition)
        if condition and not self._observer.condition_passed(observation, condition):
            detail = f"Observation condition not met: {condition}"
            if not self._handle_incident(
                session, step.id, IncidentType.EXECUTOR_FAILED, detail
            ):
                self._set_step_status(session, step, RunStepStatus.FAILED)
                return False

        self._record_trace(
            session,
            step,
            outcome,
            observation,
            provider_mode="real",
            screenshot_path=screenshot_path,
        )
        self._set_step_status(session, step, RunStepStatus.SUCCEEDED)
        run_sessions.emit_event(
            session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id
        )
        return True

    def _run_observation_action(
        self,
        session: RunSession,
        step: WorkflowStep,
        profile: InstrumentProfileContract | None,
        bindings: dict[str, str],
    ) -> bool:
        """Handle wait_until (polling) and screenshot_check (one-shot) actions."""

        run_sessions = self._run_sessions
        condition = normalize_condition(step.condition)
        if not condition:
            run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail="wait_until/screenshot_check missing condition",
            )
            self._set_step_status(session, step, RunStepStatus.FAILED)
            return False

        sources = self._step_observation_sources(step, bindings, condition)
        if not sources:
            run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail="wait_until/screenshot_check missing observation source",
            )
            self._set_step_status(session, step, RunStepStatus.FAILED)
            return False

        timeout = max(float(condition.get("timeout_seconds", 30.0)), 0.0)
        poll_interval = max(float(condition.get("poll_interval_seconds", 1.0)), 0.1)

        if step.action == "screenshot_check":
            observation, screenshot_path = self._observe_sources(session, step, profile, sources)
            passed = self._observer.condition_passed(observation, condition)
            self._set_step_status(
                session,
                step,
                RunStepStatus.OBSERVED if passed else RunStepStatus.FAILED,
            )
            self._emit_observation_event(
                session,
                step,
                observation,
                sources,
                screenshot_path=screenshot_path,
            )
            self._record_trace(
                session,
                step,
                ActionOutcome(ok=passed, detail="screenshot_check"),
                observation,
                provider_mode="real",
                poll_attempts=1,
                elapsed_seconds=0.0,
                screenshot_path=screenshot_path,
            )
            if not passed:
                self._handle_incident(
                    session,
                    step.id,
                    IncidentType.EXECUTOR_FAILED,
                    f"screenshot_check condition not met: {condition}",
                )
                return False
            run_sessions.emit_event(
                session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id
            )
            return True

        start = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            observation, screenshot_path = self._observe_sources(
                session, step, profile, sources
            )
            if self._observer.condition_passed(observation, condition):
                elapsed = time.monotonic() - start
                self._set_step_status(session, step, RunStepStatus.OBSERVED)
                self._emit_observation_event(
                    session,
                    step,
                    observation,
                    sources,
                    screenshot_path=screenshot_path,
                )
                self._record_trace(
                    session,
                    step,
                    ActionOutcome(ok=True, detail=f"wait_until hit on attempt {attempts}"),
                    observation,
                    provider_mode="real",
                    poll_attempts=attempts,
                    elapsed_seconds=elapsed,
                    screenshot_path=screenshot_path,
                )
                run_sessions.emit_event(
                    session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id
                )
                return True

            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                self._set_step_status(session, step, RunStepStatus.FAILED)
                self._emit_observation_event(
                    session,
                    step,
                    observation,
                    sources,
                    screenshot_path=screenshot_path,
                )
                self._record_trace(
                    session,
                    step,
                    ActionOutcome(ok=False, detail=f"wait_until timeout ({timeout}s)"),
                    observation,
                    provider_mode="real",
                    poll_attempts=attempts,
                    elapsed_seconds=elapsed,
                    screenshot_path=screenshot_path,
                )
                self._handle_incident(
                    session,
                    step.id,
                    IncidentType.EXECUTOR_FAILED,
                    f"wait_until timeout: {timeout}s after {attempts} polls",
                )
                return False
            if self._run_sessions.stop_requested(session.session_id):
                self._set_step_status(session, step, RunStepStatus.FAILED)
                run_sessions.emit_event(
                    session,
                    RuntimeEventName.RUN_FAILED,
                    step_id=step.id,
                    detail=self._run_sessions.stop_reason(session.session_id),
                )
                return False
            time.sleep(poll_interval)

    def _step_observation_sources(
        self,
        step: WorkflowStep,
        bindings: dict[str, str],
        condition: dict | None = None,
    ) -> list[str]:
        condition = condition if condition is not None else normalize_condition(step.condition)
        condition = condition or {}
        source = condition.get("source") or condition.get("roi")
        if source:
            return [bindings.get(str(source), str(source))]
        if bindings:
            return list(dict.fromkeys(bindings.values()))
        if step.target:
            return [step.target]
        return []

    def _observe_sources(
        self,
        session: RunSession,
        step: WorkflowStep,
        profile: InstrumentProfileContract | None,
        sources: list[str],
    ) -> tuple[Observation, str | None]:
        screenshot_path = None
        screenshot = self._executor.screenshot(step.id)
        if screenshot:
            self._observer.configure_screenshot(screenshot)
            screenshot_path = self._run_sessions.save_screenshot(
                session.session_id,
                f"{step.id}.png",
                screenshot,
            )
        else:
            self._observer.configure_screenshot(None)
        observation = self._observer.observe_profile(profile, sources)
        return observation, screenshot_path

    def _emit_observation_event(
        self,
        session: RunSession,
        step: WorkflowStep,
        observation: Observation,
        sources: list[str],
        *,
        screenshot_path: str | None = None,
    ) -> None:
        payload = {
            "step_id": step.id,
            "min_confidence": observation.min_confidence,
            "sources": sources,
            "readings": [
                {
                    "roi": reading.roi,
                    "text": reading.text,
                    "confidence": reading.confidence,
                    "detail": reading.detail,
                }
                for reading in observation.readings
            ],
        }
        if screenshot_path:
            payload["screenshot_path"] = screenshot_path
        self._run_sessions.emit_event(
            session, RuntimeEventName.RUN_STEP_OBSERVED, **payload
        )

    def _run_with_recovery(self, session: RunSession, step: WorkflowStep, safety):
        attempt = 0
        while True:
            try:
                return self._executor.run_step(step, safety)
            except SafetyViolationError as exc:
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

    def _confirm_gate(self, session: RunSession, step_id: str, reason: str) -> bool:
        run_sessions = self._run_sessions
        run_sessions.emit_event(
            session, RuntimeEventName.RUN_BLOCKED, step_id=step_id, reason=reason
        )
        ok = self._confirm(ConfirmRequest(session.session_id, step_id, reason))
        if ok:
            run_sessions.emit_event(
                session, RuntimeEventName.RUN_RECOVERED, step_id=step_id
            )
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
        *,
        provider_mode: str | None = None,
        poll_attempts: int | None = None,
        elapsed_seconds: float | None = None,
        normalization_note: str | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        record = RunTraceRecord(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            step_id=step.id,
            observation=ObservationPayload.model_validate(
                {
                    "readings": [
                        {
                            "roi": reading.roi,
                            "text": reading.text,
                            "confidence": reading.confidence,
                            "detail": reading.detail,
                        }
                        for reading in observation.readings
                    ],
                    "min_confidence": observation.min_confidence,
                }
            ),
            action=ActionPayload(type=step.action, target=step.target),
            result=ResultPayload(status="success", detail=outcome.detail or "ok"),
            artifacts=ArtifactPayload.model_validate(
                {"screenshot": screenshot_path or outcome.screenshot_path}
                if screenshot_path or outcome.screenshot_path
                else {}
            ),
            provider_mode=provider_mode,
            poll_attempts=poll_attempts,
            elapsed_seconds=elapsed_seconds,
            normalization_note=normalization_note,
        )
        self._run_sessions.append_trace(record)

    def _fail_run(
        self,
        session: RunSession,
        *,
        detail: str,
        step_id: str | None = None,
    ) -> RunSession:
        if step_id:
            for existing in session.steps:
                if existing.step_id == step_id:
                    existing.status = RunStepStatus.FAILED
                    break
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_FAILED,
            step_id=step_id,
            detail=detail,
        )
        return session

    @staticmethod
    def _set_step_status(
        session: RunSession, step: WorkflowStep, status: RunStepStatus
    ) -> None:
        for existing in session.steps:
            if existing.step_id == step.id:
                existing.status = status
                return
        session.steps.append(RunStep(step_id=step.id, action=step.action, status=status))
