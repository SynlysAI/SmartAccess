"""SpecLabOS SmartAccess 运行事件上传器。"""

from __future__ import annotations

from uuid import uuid4


class PlatformEventUploader:
    """把 SmartAccess 本地运行事件上传到 SpecLabOS。"""

    def __init__(self, platform) -> None:
        """初始化上传器。

        Args:
            platform: SpecLabOS 平台客户端。
        """
        self._platform = platform

    def upload_event(
        self,
        run_id: str,
        event_type: str,
        status: str,
        payload: dict,
    ) -> None:
        """上传运行事件。

        Args:
            run_id: SpecLabOS 运行 ID。
            event_type: 事件类型。
            status: 运行状态。
            payload: 事件载荷。
        """
        method = getattr(self._platform, "upload_run_event", None)
        if not callable(method):
            return
        method(
            run_id,
            {
                "event_id": payload.get("event_id") or f"evt_{uuid4().hex}",
                "event_type": event_type,
                "status": status,
                "step_id": str(payload.get("step_id") or ""),
                "step_index": payload.get("step_index"),
                "payload": payload,
            },
        )
