"""进程内运行时事件总线。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from smartaccess.shared.logging import get_logger

from .runtime import RuntimeEventName

Subscriber = Callable[["RuntimeEvent"], None]


@dataclass(slots=True)
class RuntimeEvent:
    """一条运行时事件。"""

    name: RuntimeEventName
    session_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """线程安全的发布订阅事件中心。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """初始化事件总线。

        Args:
            logger: 可选日志器；为空时使用 SmartAccess 默认日志器。
        """

        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()
        self._logger = logger or get_logger()

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """注册事件订阅者。

        Args:
            callback: 事件回调函数。

        Returns:
            取消订阅函数。
        """

        with self._lock:
            self._subscribers.append(callback)

        def _unsubscribe() -> None:
            """取消当前订阅者。"""

            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return _unsubscribe

    def publish(self, event: RuntimeEvent) -> None:
        """发布事件到所有订阅者。

        Args:
            event: 要发布的事件。
        """

        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - 订阅者异常不能中断运行时
                self._logger.exception(
                    "事件订阅者处理失败: name=%s session_id=%s",
                    event.name,
                    event.session_id,
                )

    def emit(
        self,
        name: RuntimeEventName,
        *,
        session_id: str | None = None,
        **payload: Any,
    ) -> RuntimeEvent:
        """构造并发布一条事件。

        Args:
            name: 事件名称。
            session_id: 可选运行会话 ID。
            **payload: 事件载荷字段。

        Returns:
            已发布的事件对象。
        """

        event = RuntimeEvent(name=name, session_id=session_id, payload=dict(payload))
        self.publish(event)
        return event
