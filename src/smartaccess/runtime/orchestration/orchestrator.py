"""Orchestrator: runtime decision center for v2 anchor-first execution."""

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
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.run_trace import (
    ActionPayload,
    ErrorPayload,
    RunTraceRecord,
    WaitStrategyPayload,
)
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowStep
from smartaccess.shared.events import RuntimeEventName

from .executor import AnchorMissingError, Executor, ExecutorError, SafetyViolationError, WindowMissingError
from .observer import Observation, Observer
from .recovery import RecoveryEngine


@dataclass(slots=True)
class ConfirmRequest:
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
        profile: AnchorsContract | None,
        session: RunSession,
    ) -> RunSession:
        try:
            self._executor.configure_profile(profile)
            title = profile.window_signature.title_contains if profile else None
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_READY)
            self._executor.ensure_window(title)
            for step in workflow.steps:
                if self._run_sessions.stop_requested(session.session_id):
                    return self._fail_run(
                        session,
                        step_id=step.id,
                        detail=self._run_sessions.stop_reason(session.session_id),
                    )
                if not self._run_step(session, workflow, profile, step):
                    return session
        except Exception as exc:  # noqa: BLE001
            current_step = next(
                (existing for existing in session.steps if existing.status == RunStepStatus.RUNNING),
                None,
            )
            return self._fail_run(
                session,
                detail=str(exc),
                step_id=current_step.step_id if current_step else None,
            )

        self._run_sessions.emit_event(session, RuntimeEventName.RUN_COMPLETED)
        return session

    def _run_step(
        self,
        session: RunSession,
        workflow: WorkflowContract,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> bool:
        self._set_step_status(session, step, RunStepStatus.RUNNING)
        requires_confirmation = self._executor.requires_confirm(step, getattr(profile, "safety_limits", None))
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_STEP_STARTED,
            step_id=step.id,
            action=step.action,
            anchor_id=step.anchor_id,
            value=step.value,
            requires_confirmation=requires_confirmation,
            expected_text=step.expected_text,
            match_mode=step.match_mode,
            wait_seconds=step.wait_seconds,
            timeout_seconds=step.timeout_seconds,
        )

        if requires_confirmation:
            if not self._confirm_gate(session, step.id, f"{step.id} requires confirmation"):
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False

        outcome = self._run_with_recovery(session, step)
        if outcome is None:
            self._set_step_status(session, step, RunStepStatus.FAILED)
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail="step execution failed",
            )
            return False

        observation, wait_strategy, attempts, elapsed_seconds, screenshot_path = self._post_action_observation(
            session=session,
            workflow=workflow,
            profile=profile,
            step=step,
        )
        reading = observation.readings[0] if observation.readings else None
        if self._observer.is_low_confidence(observation):
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_RECOVERED,
                step_id=step.id,
                recovery="resample_after_low_confidence",
            )
            observation, wait_strategy, attempts, elapsed_seconds, screenshot_path = self._post_action_observation(
                session=session,
                workflow=workflow,
                profile=profile,
                step=step,
            )
            reading = observation.readings[0] if observation.readings else None
        matched = (
            self._observer.matches(
                reading,
                expected_text=step.expected_text,
                match_mode=step.match_mode,
            )
            if reading is not None
            else None
        )
        if step.match_mode != "none" and matched is not True:
            detail = "OCR expectation not met"
            self._record_trace(
                session=session,
                workflow=workflow,
                step=step,
                observation=observation,
                wait_strategy=wait_strategy,
                attempts=attempts,
                elapsed_seconds=elapsed_seconds,
                screenshot_path=screenshot_path,
                status="timeout" if matched is False else "failed",
                error=ErrorPayload(type="ocr_mismatch", message=detail),
            )
            self._handle_incident(session, step.id, IncidentType.EXECUTOR_FAILED, detail)
            self._set_step_status(session, step, RunStepStatus.FAILED)
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail=detail,
            )
            return False

        self._emit_observation_event(
            session,
            step,
            observation,
            wait_strategy=wait_strategy,
            attempts=attempts,
            elapsed_seconds=elapsed_seconds,
            matched=matched,
            screenshot_path=screenshot_path,
        )
        self._record_trace(
            session=session,
            workflow=workflow,
            step=step,
            observation=observation,
            wait_strategy=wait_strategy,
            attempts=attempts,
            elapsed_seconds=elapsed_seconds,
            screenshot_path=screenshot_path,
            status="success",
            error=None,
        )
        self._set_step_status(session, step, RunStepStatus.SUCCEEDED)
        self._run_sessions.emit_event(session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id)
        return True

    def _post_action_observation(
        self,
        *,
        session: RunSession,
        workflow: WorkflowContract,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> tuple[Observation, WaitStrategyPayload, int, float, str | None]:
        anchor = self._executor.anchor_for_step(step)
        if anchor is None:
            return Observation(), WaitStrategyPayload(type="fixed_wait", wait_seconds=0.0), 1, 0.0, None

        if step.match_mode == "none":
            wait_seconds = (
                step.wait_seconds
                if step.wait_seconds is not None
                else anchor.default_wait_seconds
            )
            wait_seconds = float(wait_seconds or 0.0)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            return (
                Observation(),
                WaitStrategyPayload(type="fixed_wait", wait_seconds=wait_seconds),
                1,
                wait_seconds,
                None,
            )

        timeout_seconds = (
            step.timeout_seconds
            if step.timeout_seconds is not None
            else anchor.default_wait_seconds
        )
        timeout_seconds = float(timeout_seconds or 2.0)
        start = time.monotonic()
        attempts = 0
        last_observation = Observation()
        last_screenshot_path = None
        while True:
            attempts += 1
            screenshot = self._executor.screenshot(step.id)
            if screenshot:
                self._observer.configure_screenshot(screenshot)
                last_screenshot_path = self._run_sessions.save_screenshot(
                    session.session_id,
                    f"{step.id}_observe.png",
                    screenshot,
                )
            observation = self._observer.observe_anchor(profile, step.anchor_id)
            last_observation = observation
            elapsed = time.monotonic() - start
            if observation.min_confidence < 0.6:
                self._run_sessions.emit_event(
                    session,
                    RuntimeEventName.RUN_RECOVERED,
                    step_id=step.id,
                    recovery="resample_after_low_confidence",
                )
            if self._observer.is_low_confidence(observation) and elapsed < timeout_seconds:
                time.sleep(0.5)
                continue
            reading = observation.readings[0] if observation.readings else None
            matched = (
                self._observer.matches(
                    reading,
                    expected_text=step.expected_text,
                    match_mode=step.match_mode,
                )
                if reading is not None
                else False
            )
            if matched or elapsed >= timeout_seconds:
                return (
                    observation,
                    WaitStrategyPayload(
                        type="ocr_poll",
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=0.5,
                    ),
                    attempts,
                    elapsed,
                    last_screenshot_path,
                )
            time.sleep(0.5)

    def _emit_observation_event(
        self,
        session: RunSession,
        step: WorkflowStep,
        observation: Observation,
        *,
        wait_strategy: WaitStrategyPayload,
        attempts: int,
        elapsed_seconds: float,
        matched: bool | None,
        screenshot_path: str | None = None,
    ) -> None:
        reading = observation.readings[0] if observation.readings else None
        payload = {
            "step_id": step.id,
            "anchor_id": step.anchor_id,
            "min_confidence": observation.min_confidence,
            "sources": [step.anchor_id],
            "expected_text": step.expected_text,
            "actual_text": reading.text if reading is not None else None,
            "match_mode": step.match_mode,
            "matched": matched,
            "attempts": attempts,
            "elapsed_seconds": elapsed_seconds,
            "wait_strategy": wait_strategy.model_dump(mode="json", exclude_none=True),
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
        self._run_sessions.emit_event(session, RuntimeEventName.RUN_STEP_OBSERVED, **payload)

    def _run_with_recovery(self, session: RunSession, step: WorkflowStep) -> ActionOutcome | None:
        attempts = 0
        while True:
            try:
                return self._executor.run_step(step, None)
            except SafetyViolationError as exc:
                self._handle_incident(session, step.id, IncidentType.SAFETY_LIMIT_VIOLATION, str(exc))
                return None
            except (WindowMissingError, AnchorMissingError, ExecutorError) as exc:
                if not self._handle_incident(session, step.id, self._classify(exc), str(exc)):
                    return None
                attempts += 1
                if attempts > self._max_retries:
                    return None

    def _confirm_gate(self, session: RunSession, step_id: str, reason: str) -> bool:
        self._run_sessions.emit_event(session, RuntimeEventName.RUN_BLOCKED, step_id=step_id, reason=reason)
        ok = self._confirm(ConfirmRequest(session.session_id, step_id, reason))
        if ok:
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_RECOVERED, step_id=step_id)
        return ok

    def _handle_incident(
        self,
        session: RunSession,
        step_id: str,
        incident_type: IncidentType,
        detail: str,
    ) -> bool:
        incident = self._incidents.open(
            session_id=session.session_id,
            step_id=step_id,
            incident_type=incident_type,
            detail=detail,
        )
        action = self._recovery.decide(incident)
        if self._recovery.must_wait_for_human(incident):
            confirmed = self._confirm(ConfirmRequest(session.session_id, step_id, detail, incident_type.value))
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
        *,
        session: RunSession,
        workflow: WorkflowContract,
        step: WorkflowStep,
        observation: Observation,
        wait_strategy: WaitStrategyPayload,
        attempts: int,
        elapsed_seconds: float,
        screenshot_path: str | None,
        status: str,
        error: ErrorPayload | None,
    ) -> None:
        reading = observation.readings[0] if observation.readings else None
        matched = (
            self._observer.matches(
                reading,
                expected_text=step.expected_text,
                match_mode=step.match_mode,
            )
            if reading is not None
            else None
        )
        record = RunTraceRecord(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            workflow_id=workflow.metadata.workflow_id,
            template_id=workflow.metadata.template_id,
            template_version=workflow.metadata.template_version,
            step_id=step.id,
            anchor_id=step.anchor_id,
            action=ActionPayload(type=step.action, value=step.value),
            wait_strategy=wait_strategy,
            expected_text=step.expected_text,
            actual_text=reading.text if reading is not None else None,
            match_mode=step.match_mode,
            matched=matched,
            attempts=attempts,
            elapsed_seconds=elapsed_seconds,
            screenshot_path=screenshot_path,
            status=status,  # type: ignore[arg-type]
            error=error,
            provider_mode="real",
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
    def _set_step_status(session: RunSession, step: WorkflowStep, status: RunStepStatus) -> None:
        for existing in session.steps:
            if existing.step_id == step.id:
                existing.status = status
                return
        session.steps.append(RunStep(step_id=step.id, action=step.action, status=status))
