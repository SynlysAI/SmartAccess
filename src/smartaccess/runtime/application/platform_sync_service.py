"""平台同步 outbox 服务。"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import PlatformClient, PlatformOffline
from smartaccess.shared.events.bus import EventBus
from smartaccess.shared.events.runtime import RuntimeEventName

KIND_METHOD = {
    "status": "upload_status",
    "logs": "upload_logs",
    "results": "upload_results",
}


@dataclass(slots=True)
class OutboxItem:
    """待同步平台上传项。"""

    kind: str
    payload: dict[str, Any]
    attempts: int = 0


@dataclass(slots=True)
class SyncStats:
    """平台同步统计。"""

    pending: int
    delivered: int
    failed: int = field(default=0)


class PlatformSyncService:
    """基于本地 outbox 的平台同步服务。"""

    def __init__(
        self,
        *,
        platform: PlatformClient,
        event_bus: EventBus,
        workspace_dir: Path,
        max_attempts: int = 3,
    ) -> None:
        """初始化平台同步服务。"""

        self._platform = platform
        self._event_bus = event_bus
        self._workspace_dir = Path(workspace_dir)
        self._outbox_path = self._workspace_dir / "outbox" / "platform_outbox.jsonl"
        self._max_attempts = max_attempts
        self._outbox: deque[OutboxItem] = deque()
        self._delivered = 0
        self._failed = 0
        self._load_outbox()

    def enqueue(self, kind: str, payload: dict[str, Any]) -> None:
        """加入待同步队列。"""

        if kind not in KIND_METHOD:
            raise ValueError(f"未知的同步类型: {kind}")
        self._outbox.append(OutboxItem(kind=kind, payload=payload))
        self._persist_outbox()

    def sync(self) -> SyncStats:
        """尝试同步所有待上传项一次。"""

        requeue: deque[OutboxItem] = deque()
        for _ in range(len(self._outbox)):
            item = self._outbox.popleft()
            method = getattr(self._platform, KIND_METHOD[item.kind])
            try:
                ok = bool(method(item.payload))
            except PlatformOffline as exc:
                ok = False
                self._note_failure(item, str(exc))
            except Exception as exc:  # noqa: BLE001 - 同步失败不能影响本地运行
                ok = False
                self._note_failure(item, str(exc))
            if ok:
                self._delivered += 1
            else:
                item.attempts += 1
                if item.attempts < self._max_attempts:
                    requeue.append(item)
                else:
                    self._failed += 1
        self._outbox = requeue
        self._persist_outbox()
        return self.stats()

    def stats(self) -> SyncStats:
        """返回 outbox 统计。"""

        return SyncStats(
            pending=len(self._outbox),
            delivered=self._delivered,
            failed=self._failed,
        )

    def _note_failure(self, item: OutboxItem, detail: str) -> None:
        """记录同步失败事件。"""

        self._event_bus.emit(
            RuntimeEventName.PLATFORM_SYNC_FAILED,
            kind=item.kind,
            detail=detail,
        )

    def _load_outbox(self) -> None:
        """从 JSONL 文件加载 outbox。"""

        if not self._outbox_path.exists():
            return
        for line in self._outbox_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._outbox.append(
                OutboxItem(
                    kind=str(data.get("kind") or ""),
                    payload=dict(data.get("payload") or {}),
                    attempts=int(data.get("attempts") or 0),
                )
            )

    def _persist_outbox(self) -> None:
        """把 outbox 写入 JSONL 文件。"""

        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(
                {
                    "kind": item.kind,
                    "payload": item.payload,
                    "attempts": item.attempts,
                },
                ensure_ascii=False,
            )
            for item in self._outbox
        ]
        self._outbox_path.write_text("\n".join(lines), encoding="utf-8")
