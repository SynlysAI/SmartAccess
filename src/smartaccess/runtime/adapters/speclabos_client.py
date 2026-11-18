"""SpecLabOS HTTP platform client.

The client intentionally uses urllib from the standard library so SmartAccess can
call a FastAPI-compatible SpecLabOS service without adding a hard dependency.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

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
            "upload_device_image": "/api/smartaccess/device-images",
            "sync_device": "/api/smartaccess/devices/sync",
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

    def fetch_template(
        self,
        template_id: str,
        template_version: str,
        source_device_id: str | None = None,
    ) -> dict[str, Any]:
        """拉取指定模板版本，可按执行端 ID 区分同名模板。"""

        path = self._endpoints["fetch_template"].format(
            template_id=quote(template_id, safe=""),
            template_version=quote(template_version, safe=""),
        )
        if source_device_id:
            path = f"{path}?{urlencode({'source_device_id': source_device_id})}"
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
            "published_by": str(payload.get("published_by") or "smartaccess"),
            "workflow": workflow,
        }
        return self._request("POST", self._endpoints["publish_template"], normalized)

    def delete_template(
        self,
        template_id: str,
        template_version: str,
        source_device_id: str | None = None,
    ) -> bool:
        """删除云端模板版本，可按执行端 ID 精确删除同名模板。"""

        path = self._endpoints["delete_template"].format(
            template_id=quote(template_id, safe=""),
            template_version=quote(template_version, safe=""),
        )
        if source_device_id:
            path = f"{path}?{urlencode({'source_device_id': source_device_id})}"
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

    def sync_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """把仪器档案同步到 SpecLabOS。

        Args:
            payload: 包含 device_id、node_id、name、window_title。

        Returns:
            平台响应。
        """
        return self._request("POST", self._endpoints["sync_device"], payload)

    def upload_device_image(
        self,
        source_device_id: str,
        image_path: str,
    ) -> dict[str, Any]:
        """上传执行端设备图片到 SpecLabOS。

        Args:
            source_device_id: 当前执行端 ID。
            image_path: 本地设备图片路径。

        Returns:
            平台响应。
        """
        path = Path(image_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(image_path)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = f"----SmartAccessBoundary{uuid4().hex}"
        filename = f"device-image{path.suffix.lower()}"
        body = b"".join(
            [
                (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="source_device_id"'
                    f"\r\n\r\n{source_device_id}\r\n"
                ).encode("utf-8"),
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8"),
                path.read_bytes(),
                f"\r\n--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        return self._send(
            "POST",
            self._endpoints["upload_device_image"],
            body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """发送 JSON 请求并解析响应。

        Args:
            method: HTTP 方法。
            path: 请求路径。
            payload: JSON 请求体。

        Returns:
            平台响应。
        """
        body = None
        content_type = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        return self._send(method, path, body, content_type=content_type)

    def _send(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        content_type: str | None = None,
    ) -> Any:
        """发送 HTTP 请求并解析 JSON 响应。

        Args:
            method: HTTP 方法。
            path: 请求路径。
            body: 请求体字节。
            content_type: 请求体 MIME 类型。

        Returns:
            平台响应。
        """
        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
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

