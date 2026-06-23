"""SmartAccess 远程任务消费者。"""

from __future__ import annotations

import json
from typing import Any

from smartaccess.shared.contracts.workflow import WorkflowContract


class RemoteTaskWorker:
    """消费 SpecLabOS 下发的 SmartAccess 远程运行任务。"""

    def __init__(self, *, device_id: str, facade, uploader) -> None:
        """初始化 worker。

        Args:
            device_id: 当前 SmartAccess 设备 ID。
            facade: 运行时门面。
            uploader: 平台事件上传器。
        """
        self._device_id = device_id
        self._facade = facade
        self._uploader = uploader

    def handle_message(self, payload: dict[str, Any]) -> str:
        """处理一条远程运行消息。

        Args:
            payload: RabbitMQ 消息体。

        Returns:
            处理结果状态。
        """
        run_id = str(payload.get("run_id") or "")
        device_id = str(payload.get("device_id") or "")
        if device_id != self._device_id:
            self._uploader.upload_event(
                run_id,
                "run.rejected",
                "rejected",
                {"error": f"设备不匹配: expected={self._device_id}, actual={device_id}"},
            )
            return "rejected"
        try:
            workflow = WorkflowContract.model_validate(
                self._normalize_workflow_payload(payload.get("workflow") or {})
            )
        except Exception as exc:  # noqa: BLE001
            self._uploader.upload_event(
                run_id,
                "run.rejected",
                "rejected",
                {"error": str(exc), "error_type": exc.__class__.__name__},
            )
            return "rejected"
        session = self._facade.start_run(workflow, background=True)
        self._uploader.upload_event(
            run_id,
            "run.accepted",
            "accepted",
            {
                "local_session_id": session.session_id,
                "workflow_id": workflow.metadata.workflow_id,
            },
        )
        return "accepted"

    def handle_body(self, body: bytes) -> str:
        """处理 RabbitMQ 原始消息体。

        Args:
            body: JSON 消息字节。

        Returns:
            处理结果状态。
        """
        return self.handle_message(json.loads(body.decode("utf-8")))

    @staticmethod
    def _normalize_workflow_payload(workflow: Any) -> Any:
        """补齐远程任务消息中的 workflow 默认元数据。

        Args:
            workflow: 原始 workflow 消息对象。

        Returns:
            补齐默认字段后的 workflow 对象。
        """
        if not isinstance(workflow, dict):
            return workflow
        data = dict(workflow)
        metadata = dict(data.get("metadata") or {})
        metadata.setdefault("author", "speclabos")
        metadata.setdefault("lifecycle_state", "remote")
        data["metadata"] = metadata
        return data
