"""运行监控视图模型。"""

from __future__ import annotations

from dataclasses import dataclass
import queue

from PyQt6.QtCore import pyqtSignal

from smartaccess.desktop.viewmodels.base import EventRelay, ViewModel
from smartaccess.desktop.widgets import rich_text
from smartaccess.runtime.domain.run_session import RunSession
from smartaccess.runtime.application.workflow_input_resolver import (
    RuntimeInputField,
    runtime_input_fields,
)
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events.bus import RuntimeEvent


@dataclass(slots=True)
class MonitorLogEntry:
    """运行监控日志行。"""

    timestamp: str
    level: str
    message: str
    session_id: str | None = None
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowRunSummary:
    """运行监控页展示的工作流与绑定设备摘要。"""

    workflow_id: str
    lifecycle_state: str
    template_label: str
    anchor_profile: str
    device_found: bool
    status_text: str
    title_contains: str | None = None
    match_mode: str = "equals"
    process_name: str | None = None
    anchor_count: int = 0
    ocr_anchor_count: int = 0
    actions: list[str] | None = None


class MonitoringViewModel(ViewModel):
    """运行监控页和运行时门面之间的适配层。"""

    changed = pyqtSignal()
    event_received = pyqtSignal(object)

    def __init__(self, facade, parent=None) -> None:
        """初始化运行监控视图模型。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(facade, parent)
        self._relay = EventRelay(facade, self)
        self._relay.event_received.connect(self._on_event)
        self._logs: list[MonitorLogEntry] = []
        self._active_session_id: str | None = None
        self._confirm_queues: dict[tuple[str, str], queue.Queue[bool]] = {}
        self._facade.set_confirm_handler(self._confirm_handler)

    def close(self) -> None:
        """释放事件订阅。"""

        self._facade.set_confirm_handler(None)
        self._relay.close()

    def list_workflows(self) -> list[WorkflowContract]:
        """列出可运行工作流。"""

        return self._facade.list_workflows()

    def list_sessions(self) -> list[RunSession]:
        """列出运行会话。"""

        return self._facade.recent_sessions(50)

    def runtime_input_fields(self, workflow_id: str) -> list[RuntimeInputField]:
        """返回指定工作流在运行前需要人工填写的字段。

        Args:
            workflow_id: 工作流 ID。

        Returns:
            运行前人工输入字段列表。
        """

        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        return runtime_input_fields(workflow)

    def start_run(
        self,
        workflow_id: str,
        runtime_inputs: dict[str, str] | None = None,
    ) -> RunSession:
        """启动指定工作流。

        Args:
            workflow_id: 工作流 ID。
            runtime_inputs: 运行前填写的输入步骤值。

        Returns:
            新建运行会话。
        """

        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        session = self._facade.start_run(
            workflow,
            background=True,
            runtime_inputs=runtime_inputs,
        )
        self._active_session_id = session.session_id
        self.changed.emit()
        return session

    def stop_run(self, session_id: str | None = None) -> bool:
        """请求停止运行。

        Args:
            session_id: 运行会话 ID；为空时使用当前会话。

        Returns:
            是否成功发出停止请求。
        """

        target = session_id or self._active_session_id
        if not target:
            return False
        return self._facade.request_run_stop(target, reason="用户请求停止")

    def active_session(self) -> RunSession | None:
        """返回当前选中的运行会话。"""

        if self._active_session_id is None:
            sessions = self.list_sessions()
            return sessions[0] if sessions else None
        return self._facade.get_session(self._active_session_id)

    def set_active_session(self, session_id: str | None) -> None:
        """设置当前选中的运行会话。"""

        self._active_session_id = session_id
        self.changed.emit()

    def logs(self) -> list[MonitorLogEntry]:
        """返回监控日志。"""

        return list(self._logs)

    def workflow_summary(self, workflow_id: str | None) -> WorkflowRunSummary | None:
        """返回工作流及其绑定设备的运行摘要。"""

        if not workflow_id:
            return None
        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            return None
        metadata = workflow.metadata
        anchor_profile = str(metadata.anchor_profile or "")
        template_label = self._template_label(
            metadata.template_id,
            metadata.template_version,
        )
        profile = self._facade.get_instrument(anchor_profile)
        if profile is None:
            return WorkflowRunSummary(
                workflow_id=str(metadata.workflow_id),
                lifecycle_state=str(metadata.lifecycle_state),
                template_label=template_label,
                anchor_profile=anchor_profile,
                device_found=False,
                status_text="未找到绑定设备配置",
                actions=[],
            )
        ocr_count = sum(
            1
            for anchor in profile.anchors
            if anchor.precheck is not None
            and anchor.precheck.mode in {"text", "image_text"}
        )
        return WorkflowRunSummary(
            workflow_id=str(metadata.workflow_id),
            lifecycle_state=str(metadata.lifecycle_state),
            template_label=template_label,
            anchor_profile=anchor_profile,
            device_found=True,
            status_text="已绑定设备配置",
            title_contains=profile.window_signature.title_contains,
            match_mode=profile.window_signature.match_mode or "equals",
            process_name=profile.window_signature.process_name,
            anchor_count=len(profile.anchors),
            ocr_anchor_count=ocr_count,
            actions=profile.actions,
        )

    def clear_logs(self) -> None:
        """清空运行日志。"""

        self._logs.clear()
        self.changed.emit()

    def resolve_confirmation(
        self,
        session_id: str,
        step_id: str,
        allowed: bool,
    ) -> bool:
        """Resolve a pending runtime confirmation request."""

        key = (session_id, step_id)
        pending = self._confirm_queues.get(key)
        if pending is None:
            return False
        pending.put(bool(allowed))
        return True

    def _on_event(self, event: RuntimeEvent) -> None:
        """处理运行时事件。"""

        if event.session_id:
            self._active_session_id = event.session_id
        self._logs.append(self._log_entry(event))
        self.event_received.emit(event)
        self.changed.emit()

    def _confirm_handler(self, request) -> bool:
        """Block the runtime thread until the UI resolves confirmation."""

        pending: queue.Queue[bool] = queue.Queue(maxsize=1)
        key = (request.session_id, request.step_id)
        self._confirm_queues[key] = pending
        try:
            return bool(pending.get())
        finally:
            self._confirm_queues.pop(key, None)

    @staticmethod
    def _log_entry(event: RuntimeEvent) -> MonitorLogEntry:
        """把运行事件转换成日志行。"""

        payload = event.payload
        step_id = payload.get("step_id")
        detail = payload.get("detail") or payload.get("reason") or ""
        action = payload.get("action")
        message = str(event.name.value)
        if event.name.value.startswith("run.step.precheck."):
            message = MonitoringViewModel._precheck_message(event.name.value, payload)
        else:
            boundary = MonitoringViewModel._boundary_message(
                event.name.value,
                payload,
                event.session_id,
            )
            if boundary:
                message = boundary
            if step_id:
                message = f"{message} / {step_id}"
            if action:
                message = f"{message} / {action}"
            if (
                event.name.value
                in {
                    "run.step.observed",
                    "run.step.ocr.retrying",
                    "run.failed",
                }
                and _has_ocr_payload(payload)
            ):
                message = MonitoringViewModel._append_ocr_detail(message, payload)
            if detail:
                message = f"{message} / {detail}"
        level = "INFO"
        if event.name.value.endswith("failed"):
            level = "ERROR"
        elif (
            "blocked" in event.name.value
            or "stopping" in event.name.value
            or "retrying" in event.name.value
        ):
            level = "WARN"
        return MonitorLogEntry(
            timestamp=event.timestamp.astimezone().strftime("%H:%M:%S"),
            level=level,
            message=message,
            session_id=event.session_id,
            step_id=str(step_id) if step_id else None,
        )

    @staticmethod
    def _boundary_message(
        event_name: str,
        payload: dict,
        session_id: str | None,
    ) -> str | None:
        """Return START/END run boundary message for lifecycle events."""

        if event_name == "run.started":
            label = "START"
        elif event_name == "run.completed":
            label = "END completed"
        elif event_name == "run.failed":
            label = "END failed"
        elif event_name == "run.cancelled":
            label = "END cancelled"
        else:
            return None
        if not any(
            key in payload
            for key in ("device_id", "author", "workflow_name", "workflow_id")
        ):
            return None
        device_id = payload.get("device_id") or "-"
        author = payload.get("author") or "-"
        workflow_name = payload.get("workflow_name") or payload.get("workflow_id") or "-"
        session = session_id or "-"
        return (
            f"{label} / device_id={device_id} / author={author} / "
            f"workflow={workflow_name} / session={session}"
        )

    @staticmethod
    def _append_ocr_detail(message: str, payload: dict) -> str:
        """为 OCR 观测日志追加规则和识别结果。"""

        match_mode = str(payload.get("match_mode") or "none")
        expected = payload.get("expected_text") or payload.get("expected_candidates")
        rule = rich_text.ocr_rule(match_mode, expected)
        actual_text = payload.get("actual_text") or "-"
        return (
            f"{message} / OCR规则: {rule} / OCR实际: {actual_text} / "
            f"匹配: {payload.get('matched')} / 尝试: {payload.get('attempts')} / "
            f"耗时: {float(payload.get('elapsed_seconds') or 0):.1f}s"
        )

    @staticmethod
    def _precheck_message(event_name: str, payload: dict) -> str:
        """格式化锚点执行前校验日志。"""

        labels = {
            "run.step.precheck.started": "执行前校验开始",
            "run.step.precheck.retrying": "执行前校验未通过，准备重试",
            "run.step.precheck.passed": "执行前校验通过",
            "run.step.precheck.failed": "执行前校验失败",
        }
        mode_labels = {
            "image": "图像一致",
            "text": "文字一致",
            "image_text": "图像 + 文字",
        }
        parts = [labels.get(event_name, event_name)]
        if payload.get("step_id"):
            parts.append(str(payload["step_id"]))
        if payload.get("anchor_id"):
            parts.append(f"锚点={payload['anchor_id']}")
        mode = str(payload.get("precheck_mode") or "")
        if mode:
            parts.append(f"方式={mode_labels.get(mode, mode)}")
        attempt = payload.get("attempt")
        max_attempts = payload.get("max_attempts")
        if attempt is not None and max_attempts is not None:
            parts.append(f"尝试={attempt}/{max_attempts}")
        elif max_attempts is not None:
            parts.append(f"最多尝试={max_attempts}")
        image_score = payload.get("image_score")
        image_threshold = payload.get("image_threshold")
        if image_score is not None:
            parts.append(f"相似度={float(image_score):.3f}")
            if image_threshold is not None:
                parts.append(f"阈值={float(image_threshold):.3f}")
        if payload.get("reference_text") is not None:
            parts.append(f"参考文字={payload['reference_text'] or '-'}")
        if payload.get("current_text") is not None:
            parts.append(f"当前文字={payload['current_text'] or '-'}")
        if payload.get("detail"):
            parts.append(f"原因={payload['detail']}")
        return " / ".join(parts)

    @staticmethod
    def _template_label(template_id: str | None, template_version: str | None) -> str:
        """格式化模板版本标签。"""

        if template_id and template_version:
            return f"{template_id}@{template_version}"
        if template_id:
            return str(template_id)
        return "-"


def _has_ocr_payload(payload: dict) -> bool:
    """Return whether an event payload carries OCR debug fields."""

    return (
        payload.get("match_mode") not in (None, "none")
        or payload.get("expected_text") is not None
        or payload.get("actual_text") is not None
    )
