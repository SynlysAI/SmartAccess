"""工作流运行编排器。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.run_session_service import (
    IncrementCounterError,
    IncrementCounterService,
    IncrementReservation,
    RunSessionService,
)
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
from smartaccess.shared.events.runtime import RuntimeEventName

from .executor import (
    AnchorMissingError,
    Executor,
    ExecutorError,
    SafetyViolationError,
    WindowMissingError,
)
from .observer import Observation, Observer
from .recovery import RecoveryEngine

POLL_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class ConfirmRequest:
    """人工确认请求。"""

    session_id: str
    step_id: str
    reason: str
    incident_type: str | None = None


ConfirmHandler = Callable[[ConfirmRequest], bool]


@dataclass(frozen=True, slots=True)
class ExceptionDetection:
    """一次异常弹窗识别命中。"""

    rule_id: str
    view_id: str
    anchor_id: str
    message: str
    observation: Observation
    screenshot_path: str | None


class Orchestrator:
    """协调执行器、观察器和恢复策略完成一次工作流运行。"""

    def __init__(
        self,
        *,
        executor: Executor,
        observer: Observer,
        recovery: RecoveryEngine,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        increment_counters: IncrementCounterService | None = None,
        confirm_handler: ConfirmHandler | None = None,
        max_retries: int = 2,
    ) -> None:
        """初始化工作流编排器。

        Args:
            executor: 动作执行器。
            observer: OCR 观察器。
            recovery: 恢复策略。
            run_sessions: 运行会话服务。
            incidents: 异常服务。
            confirm_handler: 人工确认回调。
            max_retries: 自动恢复最大重试次数。
        """

        self._executor = executor
        self._observer = observer
        self._recovery = recovery
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._increment_counters = increment_counters
        self._confirm: ConfirmHandler = confirm_handler or (lambda _request: True)
        self._max_retries = max_retries

    def set_confirm_handler(self, handler: ConfirmHandler | None) -> None:
        """设置人工确认回调。

        Args:
            handler: 人工确认回调；为空时默认允许继续。
        """

        self._confirm = handler or (lambda _request: True)

    def run(
        self,
        *,
        workflow: WorkflowContract,
        profile: AnchorsContract | None,
        session: RunSession,
    ) -> RunSession:
        """运行一个工作流。

        Args:
            workflow: 工作流契约。
            profile: 设备锚点配置。
            session: 运行会话。

        Returns:
            完成后的运行会话。
        """

        try:
            self._executor.configure_profile(profile)
            increment_values: dict[str, IncrementReservation] = {}
            title = profile.window_signature.title_contains if profile else None
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_READY)
            try:
                self._executor.ensure_window(title)
            except WindowMissingError as exc:
                self._emit_window_missing(
                    session,
                    profile=profile,
                    detail=str(exc),
                    step_id=None,
                )
                raise
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_STARTED)
            for step in workflow.steps:
                if self._is_stopped(session, step.id):
                    self._release_increment_counters(session)
                    return self._cancel_run(session, step_id=step.id)
                step = self._resolve_runtime_step(
                    step,
                    session=session,
                    values=increment_values,
                )
                if not self._run_step(session, workflow, profile, step):
                    self._release_increment_counters(session)
                    return session
                if self._is_stopped(session, step.id):
                    self._release_increment_counters(session)
                    return self._cancel_run(session, step_id=step.id)
        except Exception as exc:  # noqa: BLE001 - 编排层需要兜底记录失败
            self._release_increment_counters(session)
            current_step = next(
                (item for item in session.steps if item.status == RunStepStatus.RUNNING),
                None,
            )
            return self._fail_run(
                session,
                detail=str(exc),
                profile=profile,
                step_id=current_step.step_id if current_step else None,
            )
        try:
            self._commit_increment_counters(session, list(increment_values.values()))
        except IncrementCounterError as exc:
            return self._fail_run(
                session,
                detail=str(exc),
                profile=profile,
                step_id=None,
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
        """运行单个步骤。"""

        self._set_step_status(session, step, RunStepStatus.RUNNING)
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_STEP_STARTED,
            step_id=step.id,
            action=step.action,
            anchor_id=step.anchor_id,
            view_id=step.view_id,
            value=step.value,
            wait_seconds=step.wait_seconds,
            timeout_seconds=step.timeout_seconds,
            expected_text=step.expected_text,
            expected_candidates=step.expected_candidates,
            match_mode=step.match_mode,
            min_confidence=step.min_confidence,
            requires_confirmation=(
                step.requires_confirmation
                if step.action == "wait"
                else self._executor.requires_confirm(step)
            ),
        )
        detected = self._detect_exception_popup(session, profile, step)
        if detected is not None:
            self._block_on_exception_popup(session, step, detected)
            return False
        if step.action == "wait":
            return self._run_wait_step(session, workflow, profile, step)
        if self._executor.requires_confirm(step):
            allowed = self._confirm_gate(
                session,
                step.id,
                f"步骤 {step.id} 需要人工确认",
            )
            if not allowed:
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False
        outcome = self._run_with_recovery(session, step, profile)
        if outcome is None:
            self._set_step_status(session, step, RunStepStatus.FAILED)
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail="步骤执行失败",
                **self._profile_payload(profile),
            )
            return False
        return self._observe_after_action(session, workflow, profile, step)

    def _resolve_runtime_step(
        self,
        step: WorkflowStep,
        *,
        session: RunSession,
        values: dict[str, IncrementReservation],
    ) -> WorkflowStep:
        """Return a run-scoped copy with persistent incrementing input resolved."""

        if step.action != "type" or step.input_mode != "incrementing":
            return step
        rule = step.increment_rule
        if rule is None:
            return step
        key = rule.sequence_key
        reservation = values.get(key)
        if reservation is None:
            context = {
                "device_id": session.device_id or "",
                "author": session.author or "",
                "workflow_name": session.workflow_name or session.workflow_id,
                "workflow_id": session.workflow_id,
                "session": session.session_id,
            }
            if self._increment_counters is None:
                rendered = rule.pattern.format(
                    **context,
                    date=datetime.now().strftime(rule.date_format),
                    counter=rule.start,
                )
                reservation = IncrementReservation(
                    workflow_id=session.workflow_id,
                    sequence_key=key,
                    value=rule.start,
                    rendered=rendered,
                    next_value=rule.start + 1,
                )
            else:
                reservation = self._increment_counters.render(
                    workflow_id=session.workflow_id,
                    session_id=session.session_id,
                    rule=rule,
                    context=context,
                )
            values[key] = reservation
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_STEP_OBSERVED,
                step_id=step.id,
                detail=(
                    f"increment {key} value={reservation.rendered} "
                    f"next={reservation.next_value}"
                ),
            )
        return step.model_copy(update={"value": reservation.rendered})

    def _commit_increment_counters(
        self,
        session: RunSession,
        reservations: list[IncrementReservation],
    ) -> None:
        if self._increment_counters is not None:
            self._increment_counters.commit(session.session_id, reservations)

    def _release_increment_counters(self, session: RunSession) -> None:
        if self._increment_counters is not None:
            self._increment_counters.release(session.session_id)

    def _run_wait_step(
        self,
        session: RunSession,
        workflow: WorkflowContract,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> bool:
        """执行固定等待、等待 OCR 或人工确认步骤。"""

        if step.requires_confirmation:
            allowed = self._confirm_gate(
                session,
                step.id,
                f"步骤 {step.id} 需要人工确认",
            )
            if not allowed:
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False
        if step.match_mode != "none" and step.anchor_id:
            return self._observe_after_action(session, workflow, profile, step)

        wait_seconds = float(step.wait_seconds or 0.0)
        start = time.monotonic()
        while time.monotonic() - start < wait_seconds:
            detected = self._detect_exception_popup(session, profile, step)
            if detected is not None:
                self._block_on_exception_popup(session, step, detected)
                return False
            if self._is_stopped(session, step.id):
                self._record_trace(
                    session=session,
                    workflow=workflow,
                    step=step,
                    observation=Observation(),
                    wait_strategy=WaitStrategyPayload(
                        type="fixed_wait",
                        wait_seconds=wait_seconds,
                    ),
                    attempts=1,
                    elapsed_seconds=time.monotonic() - start,
                    screenshot_path=None,
                    status="cancelled",
                    error=ErrorPayload(
                        type="cancelled",
                        message=self._run_sessions.stop_reason(session.session_id),
                    ),
                )
                self._set_step_status(session, step, RunStepStatus.CANCELLED)
                self._run_sessions.cancel(
                    session.session_id,
                    reason=self._run_sessions.stop_reason(session.session_id),
                )
                return False
            time.sleep(min(0.1, max(0.0, wait_seconds - (time.monotonic() - start))))
        elapsed = time.monotonic() - start
        detected = self._detect_exception_popup(session, profile, step)
        if detected is not None:
            self._block_on_exception_popup(session, step, detected)
            return False
        self._record_trace(
            session=session,
            workflow=workflow,
            step=step,
            observation=Observation(),
            wait_strategy=WaitStrategyPayload(type="fixed_wait", wait_seconds=wait_seconds),
            attempts=1,
            elapsed_seconds=elapsed,
            screenshot_path=None,
            status="success",
            error=None,
        )
        self._emit_observation_event(
            session,
            step,
            Observation(),
            wait_strategy=WaitStrategyPayload(type="fixed_wait", wait_seconds=wait_seconds),
            attempts=1,
            elapsed_seconds=elapsed,
            matched=None,
            screenshot_path=None,
        )
        self._set_step_status(session, step, RunStepStatus.SUCCEEDED)
        self._run_sessions.emit_event(session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id)
        return True

    def _observe_after_action(
        self,
        session: RunSession,
        workflow: WorkflowContract,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> bool:
        """动作后执行固定等待或 OCR 轮询。"""

        observation, wait_strategy, attempts, elapsed, screenshot_path, detected = (
            self._post_action_observation(session, profile, step)
        )
        if detected is not None:
            self._record_trace(
                session=session,
                workflow=workflow,
                step=step,
                observation=detected.observation,
                wait_strategy=wait_strategy,
                attempts=attempts,
                elapsed_seconds=elapsed,
                screenshot_path=detected.screenshot_path,
                status="failed",
                error=ErrorPayload(type="device_popup", message=detected.message),
            )
            self._block_on_exception_popup(session, step, detected)
            return False
        reading = observation.readings[0] if observation.readings else None
        matched = self._observer.matches(
            reading,
            **self._ocr_match_kwargs(step),
        )
        if self._is_stopped(session, step.id):
            self._record_trace(
                session=session,
                workflow=workflow,
                step=step,
                observation=observation,
                wait_strategy=wait_strategy,
                attempts=attempts,
                elapsed_seconds=elapsed,
                screenshot_path=screenshot_path,
                status="cancelled",
                error=ErrorPayload(
                    type="cancelled",
                    message=self._run_sessions.stop_reason(session.session_id),
                ),
            )
            self._set_step_status(session, step, RunStepStatus.CANCELLED)
            self._run_sessions.cancel(
                session.session_id,
                reason=self._run_sessions.stop_reason(session.session_id),
            )
            return False
        if step.match_mode != "none" and matched is not True:
            detail = "OCR 结果未满足期望"
            reading = observation.readings[0] if observation.readings else None
            self._record_trace(
                session=session,
                workflow=workflow,
                step=step,
                observation=observation,
                wait_strategy=wait_strategy,
                attempts=attempts,
                elapsed_seconds=elapsed,
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
                anchor_id=step.anchor_id,
                expected_text=step.expected_text,
                expected_candidates=step.expected_candidates,
                actual_text=reading.text if reading else None,
                confidence=reading.confidence if reading else None,
                match_mode=step.match_mode,
                ignore_case=step.ignore_case,
                normalize_text=step.normalize_text,
                min_confidence=step.min_confidence,
                matched=matched,
                attempts=attempts,
                elapsed_seconds=elapsed,
                wait_strategy=wait_strategy.model_dump(mode="json", exclude_none=True),
                screenshot_path=screenshot_path,
            )
            return False
        self._emit_observation_event(
            session,
            step,
            observation,
            wait_strategy=wait_strategy,
            attempts=attempts,
            elapsed_seconds=elapsed,
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
            elapsed_seconds=elapsed,
            screenshot_path=screenshot_path,
            status="success",
            error=None,
        )
        self._set_step_status(session, step, RunStepStatus.SUCCEEDED)
        self._run_sessions.emit_event(session, RuntimeEventName.RUN_STEP_SUCCEEDED, step_id=step.id)
        return True

    def _post_action_observation(
        self,
        session: RunSession,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> tuple[
        Observation,
        WaitStrategyPayload,
        int,
        float,
        str | None,
        ExceptionDetection | None,
    ]:
        """动作后执行等待或 OCR 观察。"""

        anchor = self._executor.anchor_for_step(step)
        if step.action == "wait" and profile is not None and step.anchor_id:
            anchor = profile.anchor_for_view(step.view_id, step.anchor_id)
            if anchor is None:
                anchor = profile.anchor_map().get(step.anchor_id)
        if anchor is None:
            return Observation(), WaitStrategyPayload(type="none"), 1, 0.0, None, None
        if step.match_mode == "none":
            wait_seconds = float(step.wait_seconds or anchor.default_wait_seconds or 0.0)
            start = time.monotonic()
            while time.monotonic() - start < wait_seconds:
                detected = self._detect_exception_popup(session, profile, step)
                if detected is not None:
                    return (
                        detected.observation,
                        WaitStrategyPayload(type="fixed_wait", wait_seconds=wait_seconds),
                        1,
                        time.monotonic() - start,
                        detected.screenshot_path,
                        detected,
                    )
                if self._is_stopped(session, step.id):
                    break
                time.sleep(min(0.1, max(0.0, wait_seconds - (time.monotonic() - start))))
            elapsed = time.monotonic() - start
            return (
                Observation(),
                WaitStrategyPayload(type="fixed_wait", wait_seconds=wait_seconds),
                1,
                elapsed,
                None,
                None,
            )
        timeout_seconds = float(step.timeout_seconds or anchor.default_wait_seconds or 2.0)
        pre_wait_seconds = float(step.wait_seconds or 0.0)
        wait_start = time.monotonic()
        while time.monotonic() - wait_start < pre_wait_seconds:
            if self._is_stopped(session, step.id):
                break
            time.sleep(
                min(
                    0.1,
                    max(0.0, pre_wait_seconds - (time.monotonic() - wait_start)),
                )
            )
        wait_elapsed = time.monotonic() - wait_start
        if self._is_stopped(session, step.id):
            return (
                Observation(),
                WaitStrategyPayload(
                    type="ocr_poll",
                    wait_seconds=pre_wait_seconds,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=POLL_INTERVAL_SECONDS,
                ),
                0,
                wait_elapsed,
                None,
                None,
            )
        start = time.monotonic()
        attempts = 0
        last_observation = Observation()
        last_screenshot_path = None
        while True:
            attempts += 1
            detected = self._detect_exception_popup(session, profile, step)
            if detected is not None:
                return (
                    detected.observation,
                    WaitStrategyPayload(
                        type="ocr_poll",
                        wait_seconds=pre_wait_seconds,
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=POLL_INTERVAL_SECONDS,
                    ),
                    attempts,
                    wait_elapsed + (time.monotonic() - start),
                    detected.screenshot_path,
                    detected,
                )
            self._executor.configure_step_view(step)
            screenshot = self._executor.screenshot(step.id)
            if screenshot:
                self._observer.configure_screenshot(screenshot)
                snapshot = self._observer.anchor_snapshot(
                    profile,
                    step.anchor_id,
                    view_id=step.view_id,
                )
                last_screenshot_path = self._run_sessions.save_screenshot(
                    session.session_id,
                    f"{step.id}_observe.png",
                    snapshot or screenshot,
                )
            observation = self._observer.observe_anchor(
                profile,
                step.anchor_id,
                view_id=step.view_id,
            )
            last_observation = observation
            elapsed = time.monotonic() - start
            if self._observer.is_low_confidence(observation) and elapsed < timeout_seconds:
                self._run_sessions.emit_event(
                    session,
                    RuntimeEventName.RUN_RECOVERED,
                    step_id=step.id,
                    recovery="resample_after_low_confidence",
                )
            reading = observation.readings[0] if observation.readings else None
            matched = self._observer.matches(
                reading,
                **self._ocr_match_kwargs(step),
            )
            if matched or elapsed >= timeout_seconds or self._is_stopped(session, step.id):
                return (
                    last_observation,
                    WaitStrategyPayload(
                        type="ocr_poll",
                        wait_seconds=pre_wait_seconds,
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=POLL_INTERVAL_SECONDS,
                    ),
                    attempts,
                    wait_elapsed + elapsed,
                    last_screenshot_path,
                    None,
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    def _run_with_recovery(
        self,
        session: RunSession,
        step: WorkflowStep,
        profile: AnchorsContract | None,
    ):
        """执行步骤并按策略重试可恢复异常。"""

        attempts = 0
        while True:
            try:
                return self._executor.run_step(step)
            except SafetyViolationError as exc:
                self._handle_incident(
                    session,
                    step.id,
                    IncidentType.SAFETY_LIMIT_VIOLATION,
                    str(exc),
                    profile=profile,
                )
                return None
            except (WindowMissingError, AnchorMissingError, ExecutorError) as exc:
                if not self._handle_incident(
                    session,
                    step.id,
                    self._classify(exc),
                    str(exc),
                    profile=profile,
                ):
                    return None
                attempts += 1
                if attempts > self._max_retries:
                    return None

    def _confirm_gate(self, session: RunSession, step_id: str, reason: str) -> bool:
        """执行人工确认栅栏。"""

        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_BLOCKED,
            step_id=step_id,
            reason=reason,
        )
        ok = self._confirm(ConfirmRequest(session.session_id, step_id, reason))
        if ok:
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_RECOVERED,
                step_id=step_id,
            )
        return ok

    def _handle_incident(
        self,
        session: RunSession,
        step_id: str,
        incident_type: IncidentType,
        detail: str,
        profile: AnchorsContract | None = None,
    ) -> bool:
        """记录异常并返回是否继续。"""

        if incident_type == IncidentType.WINDOW_MISSING:
            self._emit_window_missing(
                session,
                profile=profile,
                detail=detail,
                step_id=step_id,
            )
        incident = self._incidents.open(
            session_id=session.session_id,
            step_id=step_id,
            incident_type=incident_type,
            detail=detail,
        )
        action = self._recovery.decide(incident)
        if self._recovery.must_wait_for_human(incident):
            confirmed = self._confirm(
                ConfirmRequest(
                    session.session_id,
                    step_id,
                    detail,
                    incident_type.value,
                )
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

    def _detect_exception_popup(
        self,
        session: RunSession,
        profile: AnchorsContract | None,
        step: WorkflowStep,
    ) -> ExceptionDetection | None:
        """识别设备级异常弹窗规则。"""

        if profile is None or not profile.exception_rules:
            return None
        for rule in profile.exception_rules:
            if not rule.blocking:
                continue
            anchor = profile.anchor_for_view(rule.view_id, rule.anchor_id)
            if anchor is None or anchor.observe_region is None:
                continue
            self._configure_view_for_observation(profile, rule.view_id)
            screenshot = self._executor.screenshot(f"{step.id}_{rule.id}_exception")
            if not screenshot:
                continue
            self._observer.configure_screenshot(screenshot)
            observation = self._observer.observe_anchor(
                profile,
                rule.anchor_id,
                view_id=rule.view_id,
            )
            reading = observation.readings[0] if observation.readings else None
            matched = self._observer.matches(
                reading,
                expected_text=rule.expected_text,
                match_mode=rule.match_mode,
                ignore_case=rule.ignore_case,
                normalize_text=rule.normalize_text,
                min_confidence=rule.min_confidence,
            )
            if matched is not True:
                continue
            snapshot = self._observer.anchor_snapshot(
                profile,
                rule.anchor_id,
                view_id=rule.view_id,
            )
            screenshot_path = self._run_sessions.save_screenshot(
                session.session_id,
                f"{step.id}_{rule.id}_exception.png",
                snapshot or screenshot,
            )
            return ExceptionDetection(
                rule_id=rule.id,
                view_id=rule.view_id,
                anchor_id=rule.anchor_id,
                message=rule.message or f"设备异常弹窗: {rule.id}",
                observation=observation,
                screenshot_path=screenshot_path,
            )
        return None

    def _block_on_exception_popup(
        self,
        session: RunSession,
        step: WorkflowStep,
        detected: ExceptionDetection,
    ) -> None:
        """把异常弹窗命中转成阻断事件。"""

        reading = detected.observation.readings[0] if detected.observation.readings else None
        self._incidents.open(
            session_id=session.session_id,
            step_id=step.id,
            incident_type=IncidentType.DEVICE_POPUP,
            detail=detected.message,
            emit_blocked=False,
        )
        self._set_step_status(session, step, RunStepStatus.BLOCKED)
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_BLOCKED,
            step_id=step.id,
            reason=detected.message,
            detail=detected.message,
            incident_type=IncidentType.DEVICE_POPUP.value,
            exception_rule_id=detected.rule_id,
            view_id=detected.view_id,
            anchor_id=detected.anchor_id,
            actual_text=reading.text if reading else None,
            confidence=reading.confidence if reading else None,
            screenshot_path=detected.screenshot_path,
        )

    def _configure_view_for_observation(
        self,
        profile: AnchorsContract,
        view_id: str | None,
    ) -> None:
        """配置自动化 provider 使用指定视图截图。"""

        _ = profile
        self._executor.configure_view_id(view_id)

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
        screenshot_path: str | None,
    ) -> None:
        """发布步骤观察事件。"""

        reading = observation.readings[0] if observation.readings else None
        payload = {
            "step_id": step.id,
            "anchor_id": step.anchor_id,
            "view_id": step.view_id,
            "min_confidence": observation.min_confidence,
            "required_min_confidence": step.min_confidence,
            "expected_text": step.expected_text,
            "expected_candidates": step.expected_candidates,
            "actual_text": reading.text if reading else None,
            "confidence": reading.confidence if reading else None,
            "match_mode": step.match_mode,
            "ignore_case": step.ignore_case,
            "normalize_text": step.normalize_text,
            "matched": matched,
            "attempts": attempts,
            "elapsed_seconds": elapsed_seconds,
            "wait_strategy": wait_strategy.model_dump(mode="json", exclude_none=True),
            "readings": [
                {
                    "roi": item.roi,
                    "text": item.text,
                    "confidence": item.confidence,
                    "detail": item.detail,
                }
                for item in observation.readings
            ],
        }
        if screenshot_path:
            payload["screenshot_path"] = screenshot_path
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_STEP_OBSERVED,
            **payload,
        )

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
        """写入步骤运行轨迹。"""

        reading = observation.readings[0] if observation.readings else None
        matched = self._observer.matches(
            reading,
            **self._ocr_match_kwargs(step),
        )
        record = RunTraceRecord(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            workflow_id=workflow.metadata.workflow_id,
            template_id=workflow.metadata.template_id,
            template_version=workflow.metadata.template_version,
            step_id=step.id,
            view_id=step.view_id,
            anchor_id=step.anchor_id,
            action=ActionPayload(type=step.action, value=step.value),
            wait_strategy=wait_strategy,
            expected_text=step.expected_text,
            actual_text=reading.text if reading else None,
            match_mode=step.match_mode,
            confidence=reading.confidence if reading else None,
            min_confidence=step.min_confidence,
            matched=matched,
            attempts=attempts,
            elapsed_seconds=max(0.0, elapsed_seconds),
            screenshot_path=screenshot_path,
            status=status,
            error=error,
            provider_mode="real",
        )
        self._run_sessions.append_trace(record)

    def _cancel_run(self, session: RunSession, *, step_id: str | None = None) -> RunSession:
        """按停止请求取消运行。"""

        if step_id:
            for existing in session.steps:
                if existing.step_id == step_id:
                    existing.status = RunStepStatus.CANCELLED
                    break
        self._run_sessions.cancel(
            session.session_id,
            reason=self._run_sessions.stop_reason(session.session_id),
        )
        return session

    def _fail_run(
        self,
        session: RunSession,
        *,
        detail: str,
        profile: AnchorsContract | None = None,
        step_id: str | None = None,
    ) -> RunSession:
        """标记运行失败。"""

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
            **self._profile_payload(profile),
        )
        return session

    @staticmethod
    def _ocr_match_kwargs(step: WorkflowStep) -> dict:
        """Return OCR matching options from a workflow step."""

        expected_text: object = step.expected_text
        if step.expected_candidates:
            if expected_text is None:
                expected_text = list(step.expected_candidates)
            elif isinstance(expected_text, list):
                expected_text = [*expected_text, *step.expected_candidates]
            else:
                expected_text = [expected_text, *step.expected_candidates]
            expected_text = list(dict.fromkeys(str(item) for item in expected_text))
        return {
            "expected_text": expected_text,
            "match_mode": step.match_mode,
            "ignore_case": step.ignore_case,
            "normalize_text": step.normalize_text,
            "min_confidence": step.min_confidence,
        }

    def _emit_window_missing(
        self,
        session: RunSession,
        *,
        profile: AnchorsContract | None,
        detail: str,
        step_id: str | None,
    ) -> None:
        """发布目标窗口缺失的结构化阻塞事件。"""

        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_BLOCKED,
            step_id=step_id,
            incident_type=IncidentType.WINDOW_MISSING.value,
            detail=detail,
            reason=detail,
            **self._profile_payload(profile),
        )

    @staticmethod
    def _profile_payload(profile: AnchorsContract | None) -> dict[str, str | None]:
        """返回 UI 告警需要的设备和窗口字段。"""

        if profile is None:
            return {"anchor_profile": None, "title_contains": None}
        return {
            "anchor_profile": profile.profile_id,
            "title_contains": profile.window_signature.title_contains,
        }

    def _is_stopped(self, session: RunSession, step_id: str | None = None) -> bool:
        """返回会话是否收到停止请求。"""

        _ = step_id
        return self._run_sessions.stop_requested(session.session_id)

    @staticmethod
    def _classify(exc: Exception) -> IncidentType:
        """把异常映射为异常类型。"""

        if isinstance(exc, WindowMissingError):
            return IncidentType.WINDOW_MISSING
        if isinstance(exc, AnchorMissingError):
            return IncidentType.ANCHOR_MISSING
        return IncidentType.EXECUTOR_FAILED

    @staticmethod
    def _set_step_status(
        session: RunSession,
        step: WorkflowStep,
        status: RunStepStatus,
    ) -> None:
        """更新会话中的步骤状态。"""

        for existing in session.steps:
            if existing.step_id == step.id:
                existing.status = status
                return
        session.steps.append(RunStep(step_id=step.id, action=step.action, status=status))
