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
        self.last_reasoning = ""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload)
            message = data["choices"][0]["message"]
            content = message["content"]
            # DeepSeek-reasoner returns the chain-of-thought separately; capture
            # it so the workflow page can show the model's analysis (item 13).
            reasoning = message.get("reasoning_content") or ""
            workflow_data = self._extract_structured(content)
            self.last_reasoning = self._format_reasoning(
                reasoning, workflow_data, prompt, context
            )
            return WorkflowContract.model_validate(workflow_data)
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## 生成失败\n\n```\n{exc}\n```"
            raise RuntimeError(f"DeepSeek 工作流生成失败: {exc}") from exc

    @staticmethod
    def _format_reasoning(reasoning, workflow_data, prompt, context) -> str:
        lines = [
            "## DeepSeek 编排推理过程",
            f"**模型**：`{context.get('instrument_profile', '')}` 上下文 · 目标：{prompt.strip()[:120]}",
            "",
        ]
        if reasoning:
            lines += ["### 模型思考", reasoning.strip(), ""]
        else:
            lines += [
                "### 模型分析",
                "（当前模型未单独返回思维链；以下为对生成结果的结构化解读）",
                "",
            ]
        steps = workflow_data.get("steps", []) if isinstance(workflow_data, dict) else []
        if steps:
            lines.append("### 生成的步骤序列")
            for i, s in enumerate(steps, 1):
                tgt = f" → `{s.get('target')}`" if s.get("target") else ""
                val = f" = {s.get('value')}" if s.get("value") is not None else ""
                lines.append(f"{i}. **{s.get('id')}** · {s.get('action')}{tgt}{val}")
        return "\n".join(lines)

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "你是 SmartAccess 工作流设计器。只输出一个 JSON 对象，不要 Markdown。\n"
            "JSON 必须严格符合 WorkflowContract 格式：\n"
            "{\n"
            '  "metadata": {"workflow_id": "...", "author": "...", "instrument_profile": "...", "experiment_type": "...", "lifecycle_state": "Draft"},\n'
            '  "preconditions": [],\n'
            '  "roi_bindings": {},  // 必须是对象，不是数组\n'
            '  "steps": [{"id": "step_1", "action": "click", "target": "anchor_id", "value": null}],  // 使用 target 和 value，不是 anchor 和 params\n'
            '  "outputs": [{"key": "output_name", "source": "roi_id"}],\n'
            '  "retry_policy": {"max_attempts": 2}\n'
            "}\n"
            "重要：steps 中的每个步骤必须使用 'target' 字段（不是 'anchor'），'value' 字段（不是 'params'）。\n"
            "只能使用已校准的 anchors/actions，危险步骤必须保留原始 step id 以便人工确认。"
        )
        user = {
            "user_prompt": prompt,
            "context": context,
            "required_metadata": {
                "workflow_id": context.get("workflow_id", "wf_draft"),
                "instrument_profile": context.get("instrument_profile", "unknown_device"),
                "experiment_type": context.get("experiment_type", "generic_automation"),
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
