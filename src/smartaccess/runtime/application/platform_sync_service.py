"""PlatformSyncService: outbox-based sync to SpecLabOS.

Implements the MVP outbox pattern (software-design §8.3): runtime events are
enqueued locally and delivered to SpecLabOS via the :class:`PlatformClient`
port. Delivery failures stay queued for retry and emit ``platform.sync.failed``
so a network outage never blocks local execution (PRD §10.3).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from smartaccess.runtime.application.ports import PlatformClient, PlatformOffline
from smartaccess.shared.events import EventBus, RuntimeEventName

_KIND_METHOD = {
    "status": "upload_status",
    "logs": "upload_logs",
    "results": "upload_results",
}


@dataclass(slots=True)
class OutboxItem:
    """A pending platform upload."""

    kind: str
    payload: dict[str, Any]
    attempts: int = 0


@dataclass(slots=True)
class SyncStats:
    """Snapshot of the outbox for the dashboard."""

    pending: int
    delivered: int
    failed: int = field(default=0)


class PlatformSyncService:
    """Queues and delivers platform uploads with offline-safe retries."""

    def __init__(
        self, *, platform: PlatformClient, event_bus: EventBus, max_attempts: int = 3
    ) -> None:
        self._platform = platform
        self._event_bus = event_bus
        self._max_attempts = max_attempts
        self._outbox: deque[OutboxItem] = deque()
        self._delivered = 0
        self._failed = 0

    def enqueue(self, kind: str, payload: dict[str, Any]) -> None:
        if kind not in _KIND_METHOD:
            raise ValueError(f"未知的同步类型: {kind}")
        self._outbox.append(OutboxItem(kind=kind, payload=payload))

    def sync(self) -> SyncStats:
        """Attempt to deliver every queued item once, FIFO.

        Items that fail are re-queued (until ``max_attempts``) and emit
        ``platform.sync.failed``; the method never raises on delivery errors.
        """

        requeue: deque[OutboxItem] = deque()
        for _ in range(len(self._outbox)):
            item = self._outbox.popleft()
            method = getattr(self._platform, _KIND_METHOD[item.kind])
            try:
                ok = bool(method(item.payload))
            except PlatformOffline as exc:
                ok = False
                self._note_failure(item, str(exc))
            else:
                if not ok:
                    self._note_failure(item, "platform rejected upload")
            if ok:
                self._delivered += 1
            else:
                item.attempts += 1
                if item.attempts < self._max_attempts:
                    requeue.append(item)
                else:
                    self._failed += 1
        self._outbox = requeue
        return self.stats()

    def stats(self) -> SyncStats:
        return SyncStats(
            pending=len(self._outbox), delivered=self._delivered, failed=self._failed
        )

    def _note_failure(self, item: OutboxItem, detail: str) -> None:
        self._event_bus.emit(
            RuntimeEventName.PLATFORM_SYNC_FAILED, kind=item.kind, detail=detail
        )
