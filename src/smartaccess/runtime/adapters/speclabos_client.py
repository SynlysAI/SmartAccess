"""SpecLabOS HTTP platform client.

The client intentionally uses urllib from the standard library so SmartAccess can
call a FastAPI-compatible SpecLabOS service without adding a hard dependency.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
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

    def list_templates(self) -> list[dict[str, Any]]:
        payload = self._request("GET", self._endpoints["list_templates"])
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("templates") or []
            return list(items) if isinstance(items, list) else []
        return []

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

