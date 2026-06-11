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
            "## 工作流编排摘要",
            f"**模型**：`{context.get('instrument_profile', '')}` 上下文 · 目标：{prompt.strip()[:120]}",
            "",
        ]
        hits = context.get("_knowledge_hits") or []
        lines.append("### 知识命中")
        if hits:
            lines.extend(
                f"- `{hit.get('id', hit.get('title', 'knowledge'))}` · {hit.get('summary', '')}"
                for hit in hits
            )
        else:
            lines.append("- 未命中显式 Memory/Skill，按当前锚点集和内置规则生成。")
        lines.append("")
        lines.append("### 显式上下文")
        if prompt_references:
            lines.extend(
                f"- `{ref.get('token')}` → {ref.get('category')} / {ref.get('ref_id')}"
                for ref in prompt_references
            )
        else:
            lines.append("- 无显式引用，按完整设备上下文推断。")
        lines.append("")
        if reasoning:
            lines += ["### 模型摘要", "供应商返回了额外分析内容，已折叠为结构化编排摘要。", ""]
        else:
            lines += [
                "### 模型分析",
                "（当前模型未单独返回额外分析；以下为对生成结果的结构化解读）",
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
            '  "metadata": {"workflow_id": "...", "author": "...", "anchor_profile": "...", "experiment_type": "...", "lifecycle_state": "Draft"},\n'
            '  "preconditions": [],\n'
            '  "steps": [{"id": "step_1", "action": "click", "anchor_id": "anchor_id", "value": null, "match_mode": "none", "wait_seconds": 1.0}],\n'
            '  "retry_policy": {"max_attempts": 2}\n'
            "}\n"
            "steps[].action 只能是 click、type、hotkey、press_enter。\n"
            "禁止生成 double_click、wait、wait_until、screenshot_check。\n"
            "等待不是动作：固定等待写 wait_seconds；OCR 等待写 expected_text、match_mode、timeout_seconds。\n"
            "OCR 条件只使用 expected_text/match_mode/timeout_seconds，不要生成 source/mode/template/color/presence。\n"
            "不要生成 roi_bindings 或 outputs；运行结果由 run_trace.jsonl 的 OCR 事实读取。\n"
            "只能使用已校准的 anchors/actions，危险步骤必须保留原始 step id 以便人工确认。\n"
            "如果 user_prompt 或 context.prompt_references 提供了显式引用 token，优先围绕这些 ref_id 组织步骤。\n"
            "\n"
            "## 时间单位规则（极其重要！）\n"
            "所有等待时间单位必须为**秒(seconds)**，绝对不能使用毫秒。\n"
            "- wait_seconds 和 timeout_seconds 都是秒。\n"
            "- 永远不要输出 5000、3000 这样的毫秒值作为等待时间。\n"
            + knowledge_hint
        )
        user = {
            "user_prompt": prompt,
            "context": context,
            "required_metadata": {
                "workflow_id": context.get("workflow_id", "wf_draft"),
                "anchor_profile": context.get("anchor_profile") or context.get("instrument_profile", "unknown_device"),
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
        workflow_data.pop("roi_bindings", None)
        workflow_data.pop("outputs", None)
        for step in workflow_data.get("steps", []):
            if "anchor_id" not in step and step.get("target"):
                step["anchor_id"] = step.get("target")

            for field in ("wait_seconds", "timeout_seconds"):
                if step.get(field) is None:
                    continue
                val_str = str(step[field])
                ms_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:ms|毫秒)$", val_str.strip())
                if ms_match:
                    step[field] = float(ms_match.group(1)) / 1000.0
                    notes.append(f"step {step.get('id')}: {field} {val_str} -> {step[field]}s")
                    continue
                try:
                    num_val = float(val_str)
                except (ValueError, TypeError):
                    continue
                if num_val >= 1000:
                    step[field] = num_val / 1000.0
                    notes.append(f"step {step.get('id')}: {field} {num_val} -> {step[field]}s")

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
                if "expected_text" not in step and condition.get("expected") is not None:
                    step["expected_text"] = str(condition.get("expected"))
                if "match_mode" not in step:
                    operator = condition.get("operator") or "contains"
                    step["match_mode"] = "not_empty" if operator == "exists" else operator
                if "timeout_seconds" not in step and condition.get("timeout_seconds") is not None:
                    step["timeout_seconds"] = condition.get("timeout_seconds")

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
