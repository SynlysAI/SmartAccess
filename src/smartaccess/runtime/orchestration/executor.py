"""Executor: translate workflow steps into UI-level actions.

Wraps the :class:`AutomationProvider` port. Before running an action it checks
the window is present, the target anchor is locatable, and the value satisfies
the instrument's safety limits (SPEC §5.4). Failures raise typed errors the
orchestrator maps onto incident types.
"""

from __future__ import annotations

from smartaccess.runtime.application.ports import ActionOutcome, AutomationProvider
from smartaccess.shared.contracts.instrument_profile import SafetyLimits
from smartaccess.shared.contracts.workflow import WorkflowStep


class ExecutorError(RuntimeError):
    """Generic executor failure."""


class WindowMissingError(ExecutorError):
    """The instrument window could not be located."""


class AnchorMissingError(ExecutorError):
    """A target anchor could not be located."""


class SafetyViolationError(ExecutorError):
    """A parameter or action violated the instrument safety limits."""


class Executor:
    """Runs action primitives against the automation provider."""

    def __init__(self, automation: AutomationProvider) -> None:
        self._automation = automation

    def configure_profile(self, profile) -> None:
        configure = getattr(self._automation, "configure_profile", None)
        if callable(configure):
            configure(profile)

    def ensure_window(self, title_contains: str | None) -> None:
        if not self._automation.window_present(title_contains):
            raise WindowMissingError(f"未找到窗口: {title_contains}")

    def requires_confirm(self, step: WorkflowStep, safety: SafetyLimits | None) -> bool:
        return bool(safety and step.id in safety.requires_manual_confirm_for)

    def check_safety(self, step: WorkflowStep, safety: SafetyLimits | None) -> None:
        if safety is None or step.value is None:
            return
        try:
            value = float(step.value)
        except (TypeError, ValueError):
            return
        if safety.max_voltage is not None and value > safety.max_voltage:
            raise SafetyViolationError(f"参数越界: {value} > max {safety.max_voltage}")
        if safety.min_voltage is not None and value < safety.min_voltage:
            raise SafetyViolationError(f"参数越界: {value} < min {safety.min_voltage}")

    def run_step(self, step: WorkflowStep, safety: SafetyLimits | None) -> ActionOutcome:
        self.check_safety(step, safety)
        if step.target and not self._automation.locate_anchor(step.target):
            raise AnchorMissingError(f"未找到锚点: {step.target}")
        outcome = self._automation.run_action(step.action, step.target, step.value)
        if not outcome.ok:
            raise ExecutorError(outcome.detail or "动作执行失败")
        return outcome

    def screenshot(self, label: str) -> bytes:
        return self._automation.screenshot(label)
