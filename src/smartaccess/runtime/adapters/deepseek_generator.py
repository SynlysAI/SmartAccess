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
        self._normalization_notes: list[str] = []
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload)
            message = data["choices"][0]["message"]
            content = message["content"]
            # DeepSeek-reasoner returns the chain-of-thought separately; capture
            # it so the workflow page can show the model's analysis (item 13).
            reasoning = message.get("reasoning_content") or ""
            workflow_data = self._extract_structured(content)
            workflow_data = self._normalize_wait_values(workflow_data)
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
        prompt_references = context.get("prompt_references") or []
        lines = [
            "## DeepSeek 编排推理过程",
            f"**模型**：`{context.get('instrument_profile', '')}` 上下文 · 目标：{prompt.strip()[:120]}",
            "",
        ]
        lines.append("### 已引用上下文")
        if prompt_references:
            lines.extend(
                f"- `{ref.get('token')}` → {ref.get('category')} / {ref.get('ref_id')}"
                for ref in prompt_references
            )
        else:
            lines.append("- 无显式引用，按完整设备上下文推断。")
        lines.append("")
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
        knowledge_hint = ""
        hits = context.get("_knowledge_hits")
        if hits:
            knowledge_hint = (
                "\n## 来自之前运行的已知模式（优先参考）\n"
                + "\n".join(f"- {h.get('title', h.get('id', ''))}: {h.get('summary', '')}" for h in hits)
                + "\n"
            )
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
            "只能使用已校准的 anchors/actions，危险步骤必须保留原始 step id 以便人工确认。\n"
            "如果 user_prompt 或 context.prompt_references 提供了显式引用 token，优先围绕这些 ref_id 组织步骤、ROI 绑定和 outputs。\n"
            "\n"
            "## 时间单位规则（极其重要！）\n"
            "所有等待时间单位必须为**秒(seconds)**，绝对不能使用毫秒。\n"
            "- wait 的 value 是秒数，例如等待 3 秒应写 value: 3，不是 value: 3000。\n"
            "- wait_until 和 screenshot_check 的 condition.timeout_seconds 也是秒。\n"
            "- condition.poll_interval_seconds 也是秒，默认 1.0。\n"
            "- 永远不要输出 5000、3000 这样的毫秒值作为等待时间。\n"
            + knowledge_hint
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

    def _normalize_wait_values(self, workflow_data: dict[str, Any]) -> dict[str, Any]:
        """Post-process AI output: normalize wait values from ms to seconds."""
        import re

        notes: list[str] = []
        for step in workflow_data.get("steps", []):
            action = step.get("action", "")
            value = step.get("value")

            # Normalize action value
            if action in {"wait", "wait_until", "screenshot_check"} and value is not None:
                val_str = str(value)
                # Case 1: "5000ms" or "5000 ms" → strip unit, divide
                ms_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:ms|毫秒)$", val_str.strip())
                if ms_match:
                    ms_val = float(ms_match.group(1))
                    step["value"] = ms_val / 1000.0
                    notes.append(f"step {step.get('id')}: {val_str} → {step['value']}s (ms→s)")
                else:
                    try:
                        num_val = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if num_val >= 1000:
                        step["value"] = num_val / 1000.0
                        notes.append(f"step {step.get('id')}: {num_val} → {step['value']}s (疑似毫秒，已换算)")
                    elif 301 <= num_val <= 999:
                        notes.append(
                            f"⚠ step {step.get('id')}: wait={num_val}s 超过 5 分钟，请人工确认是否为秒。"
                        )

            # Normalize condition timeout → timeout_seconds
            condition = step.get("condition")
            if isinstance(condition, dict):
                if "timeout" in condition and "timeout_seconds" not in condition:
                    legacy = condition.pop("timeout")
                    try:
                        t_val = float(str(legacy))
                    except (ValueError, TypeError):
                        t_val = 30.0
                    if t_val >= 1000:
                        condition["timeout_seconds"] = t_val / 1000.0
                        notes.append(f"step {step.get('id')} condition.timeout: {t_val}ms → {condition['timeout_seconds']}s")
                    else:
                        condition["timeout_seconds"] = t_val
                # Ensure defaults
                condition.setdefault("poll_interval_seconds", 1.0)
                condition.setdefault("timeout_seconds", 30.0)
                condition.setdefault("operator", "exists")
                condition.setdefault("mode", "ocr")

        if notes:
            self._normalization_notes = notes
        return workflow_data

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
