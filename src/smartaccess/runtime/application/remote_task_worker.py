"""SmartAccess 远程任务消费者。"""

from __future__ import annotations

import json
import logging
from typing import Any

from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events.bus import RuntimeEvent
from smartaccess.shared.events.runtime import RuntimeEventName
from smartaccess.shared.logging import get_logger

_EVENT_MAPPING: dict[RuntimeEventName, tuple[str, str]] = {
    RuntimeEventName.RUN_STARTED: ("run.started", "running"),
    RuntimeEventName.RUN_STEP_STARTED: ("step.started", "running"),
    RuntimeEventName.RUN_STEP_OBSERVED: ("step.updated", "running"),
    RuntimeEventName.RUN_STEP_SUCCEEDED: ("step.completed", "success"),
    RuntimeEventName.RUN_BLOCKED: ("run.blocked", "blocked"),
    RuntimeEventName.RUN_RECOVERED: ("run.recovered", "running"),
    RuntimeEventName.RUN_COMPLETED: ("run.completed", "success"),
    RuntimeEventName.RUN_FAILED: ("run.failed", "failed"),
    RuntimeEventName.RUN_CANCELLED: ("run.cancelled", "cancelled"),
}

_LOG_EVENT_LABELS: dict[RuntimeEventName, str] = {
    RuntimeEventName.RUN_STARTED: "运行开始",
    RuntimeEventName.RUN_STEP_STARTED: "步骤开始",
    RuntimeEventName.RUN_STEP_OBSERVED: "OCR 观察",
    RuntimeEventName.RUN_STEP_SUCCEEDED: "步骤完成",
    RuntimeEventName.RUN_BLOCKED: "运行阻塞",
    RuntimeEventName.RUN_RECOVERED: "运行恢复",
    RuntimeEventName.RUN_COMPLETED: "运行完成",
    RuntimeEventName.RUN_FAILED: "运行失败",
    RuntimeEventName.RUN_CANCELLED: "运行取消",
}


class RemoteTaskWorker:
    """消费 SpecLabOS 下发的 SmartAccess 远程运行任务。

    启动本地运行后通过 EventBus 订阅步骤事件并回传到 SpecLabOS。
    """

    def __init__(self, *, device_id: str, facade, uploader) -> None:
        """初始化 worker。

        Args:
            device_id: 当前 SmartAccess 执行端电脑 ID。
            facade: 运行时门面。
            uploader: 平台事件上传器。
        """
        self._device_id = device_id
        self._facade = facade
        self._uploader = uploader
        self._run_map: dict[str, str] = {}
        self._step_index_map: dict[str, dict[str, int]] = {}
        self._logger = get_logger()
        facade.subscribe(self._on_runtime_event)

    def handle_message(self, payload: dict[str, Any]) -> str:
        """处理一条远程运行消息。

        Args:
            payload: RabbitMQ 消息体。

        Returns:
            处理结果状态。
        """
        run_id = str(payload.get("run_id") or "")
        smartaccess_node_id = str(payload.get("smartaccess_node_id") or "")
        if smartaccess_node_id != self._device_id:
            self._uploader.upload_event(
                run_id,
                "run.rejected",
                "rejected",
                {
                    "error": (
                        "SmartAccess 执行端不匹配: "
                        f"expected={self._device_id}, actual={smartaccess_node_id}"
                    )
                },
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
        self._run_map[session.session_id] = run_id
        self._step_index_map[run_id] = {
            step.id: idx for idx, step in enumerate(workflow.steps)
        }
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

    def _on_runtime_event(self, event: RuntimeEvent) -> None:
        """订阅运行时事件并回传到 SpecLabOS。

        Args:
            event: 本地运行时事件。
        """
        run_id = self._run_map.get(event.session_id or "")
        if not run_id:
            return
        mapped = _EVENT_MAPPING.get(event.name)
        if not mapped:
            return
        event_type, status = mapped
        step_id = str(event.payload.get("step_id") or "")
        step_index = (
            self._step_index_map.get(run_id, {}).get(step_id)
            if step_id
            else None
        )

        label = _LOG_EVENT_LABELS.get(event.name, event.name.value)
        extra_parts: list[str] = []
        if step_id:
            extra_parts.append(f"step={step_id}")
        if step_index is not None:
            extra_parts.append(f"index={step_index + 1}")
        if status:
            extra_parts.append(f"status={status}")

        obs_info = ""
        payload_detail = event.payload.get("detail", "")
        if event.name == RuntimeEventName.RUN_STEP_OBSERVED:
            actual = event.payload.get("actual_text", "")
            expected = event.payload.get("expected_text", "")
            matched = event.payload.get("matched", False)
            confidence = event.payload.get("confidence")
            obs_info = (
                f" | expected='{expected}' actual='{actual}' "
                f"matched={matched} confidence={confidence}"
            )
        elif event.name == RuntimeEventName.RUN_FAILED:
            error = event.payload.get("error", "") or payload_detail
            obs_info = f" | error={error}"
        elif payload_detail:
            obs_info = f" | {payload_detail}"

        self._logger.info(
            "[远程任务] %s | run_id=%s %s%s",
            label,
            run_id,
            " ".join(extra_parts) if extra_parts else "",
            obs_info,
        )

        try:
            self._uploader.upload_event(
                run_id,
                event_type,
                status,
                {
                    "step_id": step_id,
                    "step_index": step_index,
                    "detail": payload_detail,
                    "error": event.payload.get("error", ""),
                    "trace": event.payload,
                },
            )
        except Exception:  # noqa: BLE001 - 上传失败不应阻断本地运行
            self._logger.exception(
                "[远程任务] 事件上传失败 | run_id=%s event_type=%s step=%s",
                run_id,
                event_type,
                step_id or "-",
            )
