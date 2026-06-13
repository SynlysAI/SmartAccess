"""桌面视图模型基础类。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.events.bus import RuntimeEvent


class EventRelay(QObject):
    """把运行时事件转发为 Qt 信号。"""

    event_received = pyqtSignal(object)

    def __init__(self, facade: RuntimeFacade, parent: QObject | None = None) -> None:
        """初始化事件转发器。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(parent)
        self._unsubscribe = facade.subscribe(self._on_event)

    def close(self) -> None:
        """取消运行时事件订阅。"""

        self._unsubscribe()

    def _on_event(self, event: RuntimeEvent) -> None:
        """收到运行时事件后发出 Qt 信号。"""

        self.event_received.emit(event)


class ViewModel(QObject):
    """页面视图模型基类。"""

    changed = pyqtSignal()

    def __init__(self, facade: RuntimeFacade, parent: QObject | None = None) -> None:
        """初始化视图模型。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(parent)
        self._facade = facade

    @property
    def facade(self) -> RuntimeFacade:
        """返回运行时门面。"""

        return self._facade
