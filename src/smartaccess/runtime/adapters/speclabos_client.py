"""SpecLabOS HTTP platform client.

The client intentionally uses urllib from the standard library so SmartAccess can
call a FastAPI-compatible SpecLabOS service without adding a hard dependency.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from smartaccess.runtime.application.ports import PlatformOffline, TemplateVersionMissing


class SpecLabOSPlatformClient:
    """HTTP implementation of the PlatformClient port."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        endpoints: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._endpoints = {
            "health": "/health",
            "fetch_task": "/smartaccess/tasks/next",
            "fetch_template": "/api/smartaccess/templates/{template_id}/versions/{template_version}",
            "list_templates": "/api/smartaccess/templates",
            "publish_template": "/api/smartaccess/templates/publish",
            "delete_template": "/api/smartaccess/templates/{template_id}/versions/{template_version}",
            "upload_status": "/api/smartaccess/runs/{run_id}/events",
            "upload_logs": "/smartaccess/logs",
            "upload_results": "/smartaccess/results",
            "report_heartbeat": "/api/smartaccess/nodes/heartbeat",
            "register_node": "/api/smartaccess/nodes/register",
            **(endpoints or {}),
        }

    def health(self) -> bool:
        try:
            self._request("GET", self._endpoints["health"])
        except PlatformOffline:
            return False
        return True

    def fetch_task(self) -> dict[str, Any] | None:
        return self._request("GET", self._endpoints["fetch_task"])

    def fetch_template(self, template_id: str, template_version: str) -> dict[str, Any]:
        path = self._endpoints["fetch_template"].format(
            template_id=quote(template_id, safe=""),
            template_version=quote(template_version, safe=""),
        )
        try:
            return self._request("GET", path)
        except PlatformOffline as exc:
            if "404" in exc.detail:
                raise TemplateVersionMissing(template_id, template_version) from exc
            raise

    def list_templates(
        self,
        *,
        device_id: str | None = None,
        source_device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出云端模板，按设备 ID 过滤。"""
        path = self._endpoints["list_templates"]
        params = {}
        if device_id:
            params["device_id"] = device_id
        if source_device_id:
            params["source_device_id"] = source_device_id
        if params:
            path = f"{path}?{urlencode(params)}"
        payload = self._request("GET", path)
        return self._extract_template_items(payload)

    @staticmethod
    def _extract_template_items(payload: Any) -> list[dict[str, Any]]:
        """从 SpecLabOS 响应中提取模板列表。

        Args:
            payload: SpecLabOS 模板列表接口响应。

        Returns:
            模板字典列表。
        """

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("items", "templates", "records", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = payload.get("data") or payload.get("result")
        if data is payload:
            return []
        return SpecLabOSPlatformClient._extract_template_items(data)

    def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow = dict(payload.get("workflow") or {})
        metadata = workflow.get("metadata", {}) if isinstance(workflow, dict) else {}
        normalized = {
            "template_id": payload["template_id"],
            "template_version": payload["template_version"],
            "workflow_id": str(
                metadata.get("workflow_id") or payload.get("workflow_id") or ""
            ),
            "name": str(metadata.get("workflow_id") or payload["template_id"]),
            "description": str(metadata.get("description") or ""),
            "anchor_profile": str(
                payload.get("anchor_profile") or metadata.get("anchor_profile") or ""
            ),
            "source_device_id": str(
                payload.get("source_device_id") or payload.get("anchor_profile") or ""
            ),
            "published_by": "smartaccess",
            "workflow": workflow,
        }
        return self._request("POST", self._endpoints["publish_template"], normalized)

    def delete_template(self, template_id: str, template_version: str) -> bool:
        """删除云端模板版本。"""

        path = self._endpoints["delete_template"].format(
            template_id=quote(template_id, safe=""),
            template_version=quote(template_version, safe=""),
        )
        try:
            self._request("DELETE", path)
        except PlatformOffline as exc:
            if "404" in exc.detail:
                raise TemplateVersionMissing(template_id, template_version) from exc
            raise
        return True

    def upload_status(self, payload: dict[str, Any]) -> bool:
        run_id = quote(
            str(payload.get("run_id") or payload.get("session_id") or ""),
            safe="",
        )
        path = self._endpoints["upload_status"].format(run_id=run_id)
        self._request("POST", path, payload)
        return True

    def upload_run_event(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """上传 SmartAccess 运行事件。

        Args:
            run_id: SpecLabOS 运行 ID。
            payload: 事件载荷。

        Returns:
            平台响应。
        """
        path = f"/api/smartaccess/runs/{quote(run_id, safe='')}/events"
        return self._request("POST", path, payload)

    def upload_logs(self, payload: dict[str, Any]) -> bool:
        self._request("POST", self._endpoints["upload_logs"], payload)
        return True

    def upload_results(self, payload: dict[str, Any]) -> bool:
        self._request("POST", self._endpoints["upload_results"], payload)
        return True

    def report_heartbeat(self, payload: dict[str, Any]) -> bool:
        """上报执行端心跳到 SpecLabOS 平台。

        Args:
            payload: 心跳载荷,包含 node_id、device_info、heartbeat_interval_seconds。

        Returns:
            平台接收成功返回 True。
        """
        self._request("POST", self._endpoints["report_heartbeat"], payload)
        return True

    def register_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        """注册并校验 SmartAccess 执行端节点身份。

        Args:
            payload: 节点注册载荷。

        Returns:
            平台注册响应。
        """

        return self._request("POST", self._endpoints["register_node"], payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 - user-configured local/API endpoint
                raw = resp.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PlatformOffline(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise PlatformOffline(f"{method} {url} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {"raw": raw.decode("utf-8", errors="replace")}

