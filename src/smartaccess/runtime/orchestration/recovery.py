"""运行异常恢复策略。"""

from __future__ import annotations

from smartaccess.runtime.domain.incident import Incident, RecoveryAction


class RecoveryEngine:
    """根据异常领域模型返回恢复动作。"""

    @staticmethod
    def decide(incident: Incident) -> RecoveryAction:
        """返回异常对应的恢复动作。

        Args:
            incident: 运行异常。

        Returns:
            恢复动作。
        """

        return incident.recovery

    @staticmethod
    def must_wait_for_human(incident: Incident) -> bool:
        """返回异常是否需要人工确认。

        Args:
            incident: 运行异常。

        Returns:
            是否需要人工确认。
        """

        return incident.requires_manual_confirm and not incident.resolved
