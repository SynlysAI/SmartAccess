"""DeepSeek-backed workflow draft generator."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from smartaccess.shared.contracts.workflow import WorkflowContract


class DeepSeekWorkflowGenerator:
    """Generate workflow drafts with DeepSeek's OpenAI-compatible chat API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self.last_error = ""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload)
            content = data["choices"][0]["message"]["content"]
            workflow_data = self._extract_structured(content)
            return WorkflowContract.model_validate(workflow_data)
        except Exception as exc:
            self.last_error = str(exc)
            raise RuntimeError(f"DeepSeek 工作流生成失败: {exc}") from exc

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "你是 SmartAccess 工作流设计器。只输出一个 JSON 对象，不要 Markdown。"
            "JSON 必须符合 workflow.yaml 合约：metadata, preconditions, roi_bindings, steps, outputs, retry_policy。"
            "只能使用已校准 anchors/actions，危险步骤必须保留原始 step id 以便人工确认。"
        )
        user = {
            "user_prompt": prompt,
            "context": context,
            "required_metadata": {
                "workflow_id": context.get("workflow_id", "wf_draft"),
                "instrument_profile": context.get("instrument_profile", "unknown_device"),
                "author": "deepseek-assistant",
                "lifecycle_state": "Draft",
            },
        }
        return {
            "model": self._model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as resp:  # noqa: S310 - explicit user-configured LLM endpoint
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

    @staticmethod
    def _extract_structured(content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json") or stripped.startswith("yaml"):
                stripped = stripped.split("\n", 1)[1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            data = yaml.safe_load(stripped)
            if not isinstance(data, dict):
                raise ValueError("模型输出不是 JSON/YAML 对象")
            return data
