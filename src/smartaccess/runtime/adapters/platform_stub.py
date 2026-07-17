"""确定性的 SpecLabOS 平台 Stub。"""

from __future__ import annotations

from typing import Any

from smartaccess.runtime.application.ports import (
    PlatformOffline,
    TemplateVersionMissing,
)


class StubPlatformClient:
    """内存版平台客户端，供本地运行和同步流程使用。"""

    def __init__(self, *, offline: bool = False) -> None:
        """初始化平台 Stub。

        Args:
            offline: 是否模拟平台离线。
        """

        self.offline = offline
        self._templates: dict[tuple[str, str], dict[str, Any]] = {}
        self.uploads: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        """返回平台是否在线。"""

        return not self.offline

    @staticmethod
    def fetch_task() -> dict[str, Any] | None:
        """返回待执行任务。"""

        return None

    def fetch_template(
        self,
        template_id: str,
        template_version: str,
    ) -> dict[str, Any]:
        """读取指定模板版本。"""

        key = (template_id, template_version)
        if key not in self._templates:
            raise TemplateVersionMissing(template_id, template_version)
        return self._templates[key]

    def list_templates(
        self,
        *,
        device_id: str | None = None,
        source_device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出模板。"""

        self._raise_if_offline("list_templates")
        templates = [dict(payload) for payload in self._templates.values()]
        if device_id:
            templates = [
                item for item in templates if item.get("anchor_profile") == device_id
            ]
        if source_device_id:
            templates = [
                item
                for item in templates
                if item.get("source_device_id") == source_device_id
            ]
        return templates

    def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发布模板。"""

        self._raise_if_offline("publish_template")
        key = (payload["template_id"], payload["template_version"])
        self._templates[key] = dict(payload)
        return {
            "ok": True,
            "template_id": key[0],
            "template_version": key[1],
        }

    def delete_template(self, template_id: str, template_version: str) -> bool:
        """删除模板版本。"""

        self._raise_if_offline("delete_template")
        key = (template_id, template_version)
        if key not in self._templates:
            raise TemplateVersionMissing(template_id, template_version)
        del self._templates[key]
        return True

    def upload_run_event(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """上传 SmartAccess 运行事件。

        Args:
            run_id: SpecLabOS 运行 ID。
            payload: 事件载荷。

        Returns:
            平台响应。
        """
        self._raise_if_offline("upload_run_event")
        self.uploads.append(("run_event", dict(payload)))
        return {"ok": True, "run_id": run_id, **payload}

    def upload_status(self, payload: dict[str, Any]) -> bool:
        """上传状态。"""

        return self._upload("status", payload)

    def upload_logs(self, payload: dict[str, Any]) -> bool:
        """上传日志。"""

        return self._upload("logs", payload)

    def upload_results(self, payload: dict[str, Any]) -> bool:
        """上传结果。"""

        return self._upload("results", payload)

    def report_heartbeat(self, payload: dict[str, Any]) -> bool:
        """上报执行端心跳。

        Args:
            payload: 心跳载荷。

        Returns:
            平台接收成功返回 True。
        """
        return self._upload("heartbeat", payload)

    def register_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        """注册并校验执行端节点身份。

        Args:
            payload: 节点注册载荷。

        Returns:
            注册结果。
        """

        self._raise_if_offline("register_node")
        return {
            "ok": True,
            "conflict": False,
            "node_id": payload.get("node_id", ""),
        }

    def _upload(self, kind: str, payload: dict[str, Any]) -> bool:
        """记录一次上传。"""

        self._raise_if_offline(f"upload_{kind}")
        self.uploads.append((kind, dict(payload)))
        return True

    def _raise_if_offline(self, operation: str) -> None:
        """平台离线时抛出异常。"""

        if self.offline:
            raise PlatformOffline(f"{operation}: platform offline")
