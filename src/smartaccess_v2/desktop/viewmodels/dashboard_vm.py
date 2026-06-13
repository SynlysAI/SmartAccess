"""运行概览视图模型。"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess_v2.desktop.viewmodels.base import EventRelay, ViewModel
from smartaccess_v2.runtime.application.workspace_service import DashboardProjection


class DashboardViewModel(ViewModel):
    """概览页和运行时门面之间的适配层。"""

    changed = pyqtSignal()

    def __init__(self, facade, parent=None) -> None:
        """初始化概览视图模型。"""

        super().__init__(facade, parent)
        self._relay = EventRelay(facade, self)
        self._relay.event_received.connect(lambda _event: self.changed.emit())

    def close(self) -> None:
        """释放事件订阅。"""

        self._relay.close()

    def dashboard(self) -> DashboardProjection:
        """返回工作区概览投影。"""

        return self._facade.dashboard()
