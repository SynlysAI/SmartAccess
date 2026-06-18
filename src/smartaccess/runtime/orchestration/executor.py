"""工作流动作执行器。"""

from __future__ import annotations

from smartaccess.runtime.application.ports import (
    ActionOutcome,
    AutomationProvider,
)
from smartaccess.shared.contracts.anchors import (
    AnchorDefinition,
    AnchorsContract,
)
from smartaccess.shared.contracts.workflow import WorkflowStep


class ExecutorError(RuntimeError):
    """通用动作执行失败。"""


class WindowMissingError(ExecutorError):
    """目标软件窗口不存在。"""


class AnchorMissingError(ExecutorError):
    """目标锚点不存在或无法定位。"""


class SafetyViolationError(ExecutorError):
    """动作参数违反安全限制。"""


class Executor:
    """把工作流步骤转换为自动化 provider 动作。"""

    def __init__(self, automation: AutomationProvider) -> None:
        """初始化动作执行器。

        Args:
            automation: 自动化 provider。
        """

        self._automation = automation
        self._profile: AnchorsContract | None = None

    def configure_profile(self, profile: AnchorsContract | None) -> None:
        """配置当前运行使用的锚点配置。

        Args:
            profile: 当前锚点配置。
        """

        self._profile = profile
        configure = getattr(self._automation, "configure_profile", None)
        if callable(configure):
            configure(profile)

    def ensure_window(self, title_contains: str | None) -> None:
        """确认目标窗口存在。

        Args:
            title_contains: 目标窗口标题包含文本。
        """

        if not self._automation.window_present(title_contains):
            raise WindowMissingError(f"未找到目标窗口: {title_contains}")

    def configure_step_view(self, step: WorkflowStep) -> None:
        """Configure automation provider for the step's calibrated view."""

        if self._profile is None:
            return
        self.configure_view_id(step.view_id)

    def configure_view_id(self, view_id: str | None) -> None:
        """Configure automation provider for a calibrated view id."""

        if self._profile is None:
            return
        view = self._profile.view_map().get(view_id or "main")
        configure = getattr(self._automation, "configure_view", None)
        if callable(configure):
            configure(view)

    def requires_confirm(self, step: WorkflowStep) -> bool:
        """返回步骤执行前是否需要人工确认。

        Args:
            step: 待执行步骤。

        Returns:
            是否需要人工确认。
        """

        if step.requires_confirmation:
            return True
        anchor = self.anchor_for_step(step)
        if anchor is None:
            return False
        return any(
            bool(binding.requires_confirmation)
            for binding in anchor.action_bindings
            if binding.action == step.action
        )

    def anchor_for_step(self, step: WorkflowStep) -> AnchorDefinition | None:
        """查找步骤绑定的锚点。

        Args:
            step: 工作流步骤。

        Returns:
            锚点定义；等待步骤或缺失时返回 None。
        """

        if step.action == "wait" or self._profile is None or step.anchor_id is None:
            return None
        anchor = self._profile.anchor_for_view(step.view_id, step.anchor_id)
        return anchor or self._profile.anchor_map().get(step.anchor_id)

    def run_step(self, step: WorkflowStep) -> ActionOutcome:
        """执行一个动作步骤。

        Args:
            step: 工作流动作步骤。

        Returns:
            自动化动作结果。
        """

        anchor = self.anchor_for_step(step)
        if anchor is None:
            raise AnchorMissingError(f"未知锚点: {step.anchor_id}")
        self.configure_step_view(step)
        view = self._profile.view_map().get(step.view_id or "main") if self._profile else None
        title = (
            view.window_signature.title_contains
            if view is not None and view.window_signature is not None
            else None
        )
        self.ensure_window(title)
        if step.action not in anchor.supported_actions:
            raise ExecutorError(
                f"锚点 {step.anchor_id} 不支持动作 {step.action}"
            )
        self._check_safety(step)
        if not self._automation.locate_anchor(step.anchor_id):
            raise AnchorMissingError(f"锚点无法定位: {step.anchor_id}")
        outcome = self._automation.run_action(step.action, step.anchor_id, step.value)
        if not outcome.ok:
            raise ExecutorError(outcome.detail or "动作执行失败")
        return outcome

    def screenshot(self, label: str) -> bytes:
        """截取当前目标窗口或桌面。

        Args:
            label: 截图标签。

        Returns:
            PNG 字节。
        """

        return self._automation.screenshot(label)

    def _check_safety(self, step: WorkflowStep) -> None:
        """检查步骤参数是否触发安全限制。"""

        if self._profile is None or step.value is None:
            return
        safety = self._profile.safety_limits
        try:
            numeric = float(step.value)
        except (TypeError, ValueError):
            return
        if safety.max_voltage is not None and numeric > safety.max_voltage:
            raise SafetyViolationError(
                f"数值 {numeric} 超过最大电压 {safety.max_voltage}"
            )
        if safety.min_voltage is not None and numeric < safety.min_voltage:
            raise SafetyViolationError(
                f"数值 {numeric} 低于最小电压 {safety.min_voltage}"
            )
