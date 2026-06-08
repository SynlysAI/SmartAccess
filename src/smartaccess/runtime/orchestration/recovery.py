"""RecoveryEngine: decide how to recover from an incident.

Recovery only decides *how* to recover; it never mutates the published template
truth source (software-design §5.2). It defers to the domain default recovery
policy and flags high-risk incidents that must wait for a manual confirmation.
"""

from __future__ import annotations

from smartaccess.runtime.domain.incident import Incident, RecoveryAction


class RecoveryEngine:
    """Maps an incident to a recovery action using the domain policy."""

    def decide(self, incident: Incident) -> RecoveryAction:
        return incident.recovery

    def must_wait_for_human(self, incident: Incident) -> bool:
        return incident.requires_manual_confirm and not incident.resolved
