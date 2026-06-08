"""View model base and the event relay that marshals bus events to the GUI thread.

The runtime :class:`EventBus` publishes from whatever thread the orchestrator
runs on (often a background worker). Qt widgets must only be touched on the GUI
thread, so :class:`EventRelay` re-emits each event as a Qt signal; Qt delivers
it on the receiver's (GUI) thread via a queued connection.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.events import RuntimeEvent


class EventRelay(QObject):
    """Bridges the thread-agnostic EventBus to thread-safe Qt signals."""

    event_received = pyqtSignal(object)  # RuntimeEvent

    def __init__(self, facade: RuntimeFacade, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._unsubscribe = facade.subscribe(self._on_event)

    def _on_event(self, event: RuntimeEvent) -> None:
        # Emitting from any thread is safe; delivery happens on the GUI thread.
        self.event_received.emit(event)

    def close(self) -> None:
        self._unsubscribe()


class ViewModel(QObject):
    """Base for page view models. Holds the facade; exposes Qt signals."""

    changed = pyqtSignal()

    def __init__(self, facade: RuntimeFacade, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade

    @property
    def facade(self) -> RuntimeFacade:
        return self._facade
