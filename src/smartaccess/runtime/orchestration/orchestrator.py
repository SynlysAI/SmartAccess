"""工作流运行编排器。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from smartaccess.runtime.application.incident_service import IncidentService
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
            title = profile.window_signature.title_contains if profile else None
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_READY)
            self._executor.ensure_window(title)
            self._run_sessions.emit_event(session, RuntimeEventName.RUN_STARTED)
            for step in workflow.steps:
                if self._is_stopped(session, step.id):
                    return self._cancel_run(session, step_id=step.id)
                if not self._run_step(session, workflow, profile, step):
                    return session
                if self._is_stopped(session, step.id):
                    return self._cancel_run(session, step_id=step.id)
        except Exception as exc:  # noqa: BLE001 - 编排层需要兜底记录失败
            current_step = next(
                (item for item in session.steps if item.status == RunStepStatus.RUNNING),
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
        """运行单个步骤。"""

        self._set_step_status(session, step, RunStepStatus.RUNNING)
        self._run_sessions.emit_event(
            session,
            RuntimeEventName.RUN_STEP_STARTED,
            step_id=step.id,
            action=step.action,
            anchor_id=step.anchor_id,
            value=step.value,
            wait_seconds=step.wait_seconds,
            timeout_seconds=step.timeout_seconds,
            expected_text=step.expected_text,
            match_mode=step.match_mode,
            requires_confirmation=(
                False if step.action == "wait" else self._executor.requires_confirm(step)
            ),
        )
        if step.action == "wait":
            return self._run_wait_step(session, workflow, step)
        if self._executor.requires_confirm(step):
            allowed = self._confirm_gate(
                session,
                step.id,
                f"步骤 {step.id} 需要人工确认",
            )
            if not allowed:
                self._set_step_status(session, step, RunStepStatus.BLOCKED)
                return False
        outcome = self._run_with_recovery(session, step)
        if outcome is None:
            self._set_step_status(session, step, RunStepStatus.FAILED)
            self._run_sessions.emit_event(
                session,
                RuntimeEventName.RUN_FAILED,
                step_id=step.id,
                detail="步骤执行失败",
            )
            return False
        return self._observe_after_action(session, workflow, profile, step)

    def _run_wait_step(
        self,
        session: RunSession,
        workflow: WorkflowContract,
        step: WorkflowStep,
    ) -> bool:
        """执行可取消的固定等待步骤。"""

        wait_seconds = float(step.wait_seconds or 0.0)
        start = time.monotonic()
        while time.monotonic() - start < wait_seconds:
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

        observation, wait_strategy, attempts, elapsed, screenshot_path = (
            self._post_action_observation(session, profile, step)
        )
        reading = observation.readings[0] if observation.readings else None
        matched = self._observer.matches(
            reading,
            expected_text=step.expected_text,
            match_mode=step.match_mode,
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
                actual_text=reading.text if reading else None,
                match_mode=step.match_mode,
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
    ) -> tuple[Observation, WaitStrategyPayload, int, float, str | None]:
        """动作后执行等待或 OCR 观察。"""

        anchor = self._executor.anchor_for_step(step)
        if anchor is None:
            return Observation(), WaitStrategyPayload(type="none"), 1, 0.0, None
        if step.match_mode == "none":
            wait_seconds = float(step.wait_seconds or anchor.default_wait_seconds or 0.0)
            start = time.monotonic()
            while time.monotonic() - start < wait_seconds:
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
            )
        timeout_seconds = float(step.timeout_seconds or anchor.default_wait_seconds or 2.0)
        start = time.monotonic()
        attempts = 0
        last_observation = Observation()
        last_screenshot_path = None
        while True:
            attempts += 1
            screenshot = self._executor.screenshot(step.id)
            if screenshot:
                self._observer.configure_screenshot(screenshot)
                snapshot = self._observer.anchor_snapshot(profile, step.anchor_id)
                last_screenshot_path = self._run_sessions.save_screenshot(
                    session.session_id,
                    f"{step.id}_observe.png",
                    snapshot or screenshot,
                )
            observation = self._observer.observe_anchor(profile, step.anchor_id)
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
                expected_text=step.expected_text,
                match_mode=step.match_mode,
            )
            if matched or elapsed >= timeout_seconds or self._is_stopped(session, step.id):
                return (
                    last_observation,
                    WaitStrategyPayload(
                        type="ocr_poll",
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=POLL_INTERVAL_SECONDS,
                    ),
                    attempts,
                    elapsed,
                    last_screenshot_path,
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    def _run_with_recovery(self, session: RunSession, step: WorkflowStep):
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
                )
                return None
            except (WindowMissingError, AnchorMissingError, ExecutorError) as exc:
                if not self._handle_incident(session, step.id, self._classify(exc), str(exc)):
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
    ) -> bool:
        """记录异常并返回是否继续。"""

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
            "min_confidence": observation.min_confidence,
            "expected_text": step.expected_text,
            "actual_text": reading.text if reading else None,
            "match_mode": step.match_mode,
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
            expected_text=step.expected_text,
            match_mode=step.match_mode,
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
            actual_text=reading.text if reading else None,
            match_mode=step.match_mode,
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
        )
        return session

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
