"""In-process event bus for runtime domain events.

The bus is the backbone for live monitoring: the orchestration loop and
application services publish :class:`RuntimeEvent` values, and subscribers
(desktop view models, loggers, platform sync) react to them. It is deliberately
tiny and dependency-free so every layer can share it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .runtime import RuntimeEventName

Subscriber = Callable[["RuntimeEvent"], None]


@dataclass(slots=True)
class RuntimeEvent:
    """A single runtime event with its originating session and payload."""

    name: RuntimeEventName
    session_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Thread-safe publish/subscribe hub for :class:`RuntimeEvent`."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Register ``callback``; returns an unsubscribe function."""

        with self._lock:
            self._subscribers.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return _unsubscribe

    def publish(self, event: RuntimeEvent) -> None:
        """Deliver ``event`` to every subscriber.

        Subscriber exceptions are swallowed so one bad listener cannot break the
        run loop; delivery order matches subscription order.
        """

        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - a listener must never break publishing
                continue

    def emit(
        self,
        name: RuntimeEventName,
        *,
        session_id: str | None = None,
        **payload: Any,
    ) -> RuntimeEvent:
        """Convenience helper to build and publish an event in one call."""

        event = RuntimeEvent(name=name, session_id=session_id, payload=dict(payload))
        self.publish(event)
        return event
