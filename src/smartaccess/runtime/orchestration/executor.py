"""Executor: translate workflow steps into UI-level actions."""

from __future__ import annotations

from smartaccess.runtime.application.ports import ActionOutcome, AutomationProvider
from smartaccess.shared.contracts.anchors import AnchorDefinition, AnchorsContract
from smartaccess.shared.contracts.workflow import WorkflowStep


class ExecutorError(RuntimeError):
    """Generic executor failure."""


class WindowMissingError(ExecutorError):
    """The application window could not be located."""


class AnchorMissingError(ExecutorError):
    """A target anchor could not be located."""


class SafetyViolationError(ExecutorError):
    """A parameter or action violated safety constraints."""


class Executor:
    """Runs action primitives against the automation provider."""

    def __init__(self, automation: AutomationProvider) -> None:
        self._automation = automation
        self._profile: AnchorsContract | None = None

    def configure_profile(self, profile: AnchorsContract | None) -> None:
        self._profile = profile
        configure = getattr(self._automation, "configure_profile", None)
        if callable(configure):
            configure(profile)

    def ensure_window(self, title_contains: str | None) -> None:
        if not self._automation.window_present(title_contains):
            raise WindowMissingError(f"window not found: {title_contains}")

    def requires_confirm(self, step: WorkflowStep, _safety) -> bool:
        if step.requires_confirmation:
            return True
        anchor = self.anchor_for_step(step)
        if anchor is None:
            return False
        return any(
            bool(getattr(binding, "requires_confirmation", False))
            for binding in anchor.action_bindings
            if getattr(binding, "action", None) == step.action
        )

    def anchor_for_step(self, step: WorkflowStep) -> AnchorDefinition | None:
        if self._profile is None:
            return None
        return self._profile.anchor_map().get(step.anchor_id)

    def run_step(self, step: WorkflowStep, _safety) -> ActionOutcome:
        anchor = self.anchor_for_step(step)
        if anchor is None:
            raise AnchorMissingError(f"unknown anchor: {step.anchor_id}")
        if step.action not in anchor.supported_actions:
            raise ExecutorError(f"unsupported action '{step.action}' for anchor '{step.anchor_id}'")
        self._check_safety(step)
        if not self._automation.locate_anchor(step.anchor_id):
            raise AnchorMissingError(f"anchor not located: {step.anchor_id}")
        outcome = self._automation.run_action(step.action, step.anchor_id, step.value)
        if not outcome.ok:
            raise ExecutorError(outcome.detail or "action failed")
        return outcome

    def screenshot(self, label: str) -> bytes:
        return self._automation.screenshot(label)

    def _check_safety(self, step: WorkflowStep) -> None:
        if self._profile is None or step.value is None:
            return
        safety = self._profile.safety_limits
        try:
            numeric = float(step.value)
        except (TypeError, ValueError):
            return
        if safety.max_voltage is not None and numeric > safety.max_voltage:
            raise SafetyViolationError(f"value {numeric} exceeds max_voltage {safety.max_voltage}")
        if safety.min_voltage is not None and numeric < safety.min_voltage:
            raise SafetyViolationError(f"value {numeric} below min_voltage {safety.min_voltage}")
