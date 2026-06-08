"""Dashboard view model: exposes the workspace projection."""

from __future__ import annotations

from smartaccess.runtime.application.workspace_service import DashboardProjection

from .base import ViewModel


class DashboardViewModel(ViewModel):
    def projection(self) -> DashboardProjection:
        return self._facade.dashboard()
