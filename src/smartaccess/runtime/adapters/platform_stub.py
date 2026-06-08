"""Deterministic platform client stub.

Stands in for the SpecLabOS HTTP client. Keeps an in-memory template store and
accepts uploads. Set ``offline=True`` to make uploads raise
:class:`PlatformOffline`, exercising the outbox retry path.
"""

from __future__ import annotations

from typing import Any

from smartaccess.runtime.application.ports import PlatformOffline, TemplateVersionMissing


class StubPlatformClient:
    """In-memory SpecLabOS stand-in for local runs and tests."""

    def __init__(self, *, offline: bool = False) -> None:
        self.offline = offline
        self._templates: dict[tuple[str, str], dict[str, Any]] = {}
        self.uploads: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        return not self.offline

    def fetch_task(self) -> dict[str, Any] | None:
        return None

    def fetch_template(self, template_id: str, template_version: str) -> dict[str, Any]:
        key = (template_id, template_version)
        if key not in self._templates:
            raise TemplateVersionMissing(template_id, template_version)
        return self._templates[key]

    def list_templates(self) -> list[dict[str, Any]]:
        if self.offline:
            raise PlatformOffline("list_templates: platform offline")
        return [dict(payload) for payload in self._templates.values()]

    def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            raise PlatformOffline("publish_template: platform offline")
        key = (payload["template_id"], payload["template_version"])
        self._templates[key] = payload
        return {"ok": True, "template_id": key[0], "template_version": key[1]}

    def upload_status(self, payload: dict[str, Any]) -> bool:
        return self._upload("status", payload)

    def upload_logs(self, payload: dict[str, Any]) -> bool:
        return self._upload("logs", payload)

    def upload_results(self, payload: dict[str, Any]) -> bool:
        return self._upload("results", payload)

    def _upload(self, kind: str, payload: dict[str, Any]) -> bool:
        if self.offline:
            raise PlatformOffline(f"upload_{kind}: platform offline")
        self.uploads.append((kind, payload))
        return True
