"""Codex Responses API workflow and anchor-profile generators.

使用 OpenAI Responses API (/responses) 格式，而非 Chat Completions (/chat/completions)。
图片通过 input_image 类型传递，不使用 text.format 参数（代理不支持）。
UA 使用 codex_vscode 标识。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from smartaccess.runtime.adapters.openai_compatible_generator import (
    OpenAICompatibleChatClient,
    OpenAICompatibleInstrumentProfileGenerator,
)
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.workflow import WorkflowContract

CODEX_USER_AGENT = (
    "codex_vscode/0.137.0-alpha.4 "
    "(Windows 10.0.26200; x86_64) unknown (VS Code; 26.602.71036)"
)


class CodexResponsesClient(OpenAICompatibleChatClient):
    """使用 Responses API (/responses) 的 Codex 客户端。

    与 Chat Completions API 的关键差异:
    - 端点: /responses 而非 /chat/completions
    - 请求: input 替代 messages, input_image 替代 image_url
    - 响应: output[].content[].text 替代 choices[].message.content
    - 不使用 text.format 参数（代理不支持）
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "Codex",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name=provider_name,
            timeout_seconds=timeout_seconds,
            user_agent=CODEX_USER_AGENT,
        )

    def _headers(self, target_base_url: str | None = None) -> dict[str, str]:
        """构建请求头，使用 codex_vscode UA，不带 Origin/Referer。"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }

    def _post_responses(self, payload: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
        """发送 POST 请求到 /responses 端点。"""
        return self._post("/responses", payload, base_url=base_url)

    @staticmethod
    def _responses_content(data: dict[str, Any]) -> str:
        """从 Responses API 返回结构中提取文本内容。

        Args:
            data: Responses API 返回的 JSON 数据。

        Returns:
            提取到的文本内容，如无匹配则返回空字符串。
        """
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return str(content.get("text", ""))
        return ""

    @staticmethod
    def _build_input_text(role: str, text: str) -> dict[str, Any]:
        """构建纯文本 input 项。

        Args:
            role: 消息角色 (system/user)。
            text: 文本内容。

        Returns:
            Responses API 格式的 input 项。
        """
        return {"role": role, "content": text}

    @staticmethod
    def _build_input_user_with_image(text: str, context: dict[str, Any]) -> str | list[dict[str, Any]]:
        """构建可能包含图片的 user input 项。

        Args:
            text: 文本内容 (JSON 字符串)。
            context: 包含 screenshot 键的上下文字典。

        Returns:
            纯文本字符串或 input_text + input_image 列表。
        """
        screenshot = context.get("screenshot")
        if not isinstance(screenshot, dict) or not screenshot.get("data"):
            return text
        mime_type = str(screenshot.get("mime_type") or "image/png")
        data = str(screenshot["data"])
        return [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": f"data:{mime_type};base64,{data}"},
        ]


class CodexWorkflowGenerator(CodexResponsesClient):
    """通过 Codex Responses API 生成工作流草稿。"""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        self._normalization_notes: list[str] = []
        base_url, _model, _provider = self._request_config(context)
        payload = self._responses_payload(prompt, context)
        try:
            data = self._post_responses(payload, base_url=base_url)
            content = self._responses_content(data)
            workflow_data = self._extract_structured(content)
            workflow_data = self._normalize_wait_values(workflow_data)
            self.last_reasoning = self._format_reasoning(
                workflow_data, prompt, context
            )
            return WorkflowContract.model_validate(workflow_data)
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n```\n{exc}\n```"
            raise RuntimeError(f"{self._provider_name} workflow generation failed: {exc}") from exc

    def _responses_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """构建 Responses API 请求负载。

        Args:
            prompt: 用户输入的自动化目标。
            context: 工作流生成所需的锚点、动作和元数据上下文。

        Returns:
            Responses API 格式的请求负载。
        """
        _base_url, model, _provider = self._request_config(context)
        knowledge_hint = ""
        hits = context.get("_knowledge_hits")
        if hits:
            knowledge_hint = (
                "\nKnown SmartAccess patterns to prioritize:\n"
                + "\n".join(f"- {h.get('title', h.get('id', ''))}: {h.get('summary', '')}" for h in hits)
                + "\n"
            )
        system = (
            "You are the SmartAccess workflow designer. Return only one JSON object, no Markdown.\n"
            "The JSON must match this simplified WorkflowContract shape:\n"
            '{"metadata":{"workflow_id":"...","author":"ai-assistant","anchor_profile":"...",'
            '"experiment_type":"...","lifecycle_state":"Draft"},'
            '"preconditions":[],"steps":[{"id":"step_1","action":"click","anchor_id":"anchor_id",'
            '"value":null,"match_mode":"none","wait_seconds":1.0}],"retry_policy":{"max_attempts":2}}\n'
            "Allowed step actions: click, type, hotkey, press_enter.\n"
            "Never output double_click, wait, wait_until, screenshot_check, roi_bindings, or outputs.\n"
            "Fixed waits use wait_seconds. OCR waits use expected_text, match_mode, and timeout_seconds.\n"
            "All wait_seconds and timeout_seconds values are seconds, never milliseconds.\n"
            "Use only calibrated anchors and actions from context."
            + knowledge_hint
        )
        user = {
            "user_prompt": prompt,
            "context": self._context_without_binary(context),
            "required_metadata": {
                "workflow_id": context.get("workflow_id", "wf_draft"),
                "anchor_profile": context.get("anchor_profile") or context.get("instrument_profile", "unknown_device"),
                "experiment_type": context.get("experiment_type", "generic_automation"),
                "author": "ai-assistant",
                "lifecycle_state": "Draft",
            },
        }
        return {
            "model": model,
            "temperature": 0.2,
            "input": [
                self._build_input_text("system", system),
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        }

    @staticmethod
    def _format_reasoning(
        workflow_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        lines = [
            "## Workflow draft",
            f"goal: {prompt.strip()[:120] or '-'}",
            f"anchor_profile: {context.get('anchor_profile') or context.get('instrument_profile') or '-'}",
            "",
            "### Steps",
        ]
        for index, step in enumerate(workflow_data.get("steps", []) or [], 1):
            value = f" = {step.get('value')}" if step.get("value") is not None else ""
            lines.append(f"{index}. {step.get('id')} - {step.get('action')} -> {step.get('anchor_id')}{value}")
        return "\n".join(lines)

    def _normalize_wait_values(self, workflow_data: dict[str, Any]) -> dict[str, Any]:
        """归一化 wait/timeout 值。"""
        import re

        notes: list[str] = []
        workflow_data.pop("roi_bindings", None)
        workflow_data.pop("outputs", None)
        for step in workflow_data.get("steps", []) or []:
            if "anchor_id" not in step and step.get("target"):
                step["anchor_id"] = step.get("target")
            for field in ("wait_seconds", "timeout_seconds"):
                if step.get(field) is None:
                    continue
                val_str = str(step[field])
                ms_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:ms|milliseconds?)$", val_str.strip(), re.IGNORECASE)
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

            condition = step.get("condition")
            if isinstance(condition, dict):
                if "timeout" in condition and "timeout_seconds" not in condition:
                    try:
                        t_val = float(str(condition.pop("timeout")))
                    except (ValueError, TypeError):
                        t_val = 30.0
                    condition["timeout_seconds"] = t_val / 1000.0 if t_val >= 1000 else t_val
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


class CodexInstrumentProfileGenerator(CodexResponsesClient):
    """通过 Codex Responses API 生成可审阅的锚点配置。"""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> AnchorsContract:
        base_url, _model, _provider = self._request_config(context)
        payload = self._responses_payload(prompt, context)
        try:
            data = self._post_responses(payload, base_url=base_url)
            content = self._responses_content(data)
            profile_data = self._normalize_anchor_profile(
                self._extract_structured(content),
                context,
            )
            self.last_reasoning = self._format_reasoning(profile_data, prompt, context)
            return AnchorsContract.model_validate(profile_data)
        except ValidationError as exc:
            self.last_error = self._friendly_validation_error(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"AI anchor suggestion is not usable: {self.last_error}") from exc
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"{self._provider_name} anchor generation failed: {self.last_error}") from exc

    def _responses_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """构建 Responses API 请求负载。

        Args:
            prompt: 用户输入的接入目标描述。
            context: 包含窗口信息、截图、设备 ID 等的上下文字典。

        Returns:
            Responses API 格式的请求负载。
        """
        _base_url, model, _provider = self._request_config(context)
        system = (
            "You are the SmartAccess device onboarding and calibration assistant. "
            "Return only one JSON object, no Markdown.\n"
            "The JSON must match the simplified anchors.yaml model:\n"
            '{"profile_id":"...","window_signature":{"title_contains":"...",'
            '"screenshot_size":{"width":0,"height":0}},"anchors":[{"id":"anchor_id",'
            '"action_region":{"pixel":{"x":0,"y":0,"width":0,"height":0},'
            '"normalized":{"x":0,"y":0,"width":0,"height":0}},"observe_region":null,'
            '"supported_actions":["click"],"default_wait_seconds":2.0,'
            '"action_bindings":[{"action":"click","requires_confirmation":false}]}]}\n'
            "Allowed actions: click, type, hotkey, press_enter.\n"
            "Each anchor has exactly one action_region and at most one OCR observe_region.\n"
            "Represent OCR only through observe_region. Do not output workflow, outputs, roi_bindings, "
            "wait, wait_until, screenshot_check, or double_click.\n"
            "If screenshot coordinates are uncertain, output a small set of suggested anchors with zero-size regions "
            "so the user can finish manual calibration."
        )
        user = {
            "user_goal": prompt,
            "context": self._context_without_binary(context),
            "required_profile": {
                "profile_id": context.get("device_id") or "new_device",
                "title_contains": context.get("title_contains") or context.get("window_title") or "",
                "capture_width": context.get("capture_width"),
                "capture_height": context.get("capture_height"),
            },
        }
        user_text = json.dumps(user, ensure_ascii=False)
        return {
            "model": model,
            "temperature": 0.2,
            "input": [
                self._build_input_text("system", system),
                {"role": "user", "content": self._build_input_user_with_image(user_text, context)},
            ],
        }

    @staticmethod
    def _format_reasoning(
        profile_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        anchors = profile_data.get("anchors", []) if isinstance(profile_data, dict) else []
        lines = [
            "## Anchor profile suggestion",
            f"goal: {prompt.strip()[:120] or 'generate anchor profile'}",
            f"window: {context.get('title_contains') or context.get('window_title') or '-'}",
            f"screenshot_attached: {bool(context.get('screenshot'))}",
            "",
            "### Suggested anchors",
        ]
        if anchors:
            for anchor in anchors:
                actions = ", ".join(anchor.get("supported_actions") or [])
                lines.append(
                    f"- {anchor.get('id')} - action_region={bool(anchor.get('action_region'))} "
                    f"- observe_region={bool(anchor.get('observe_region'))} - actions={actions or 'click'}"
                )
        else:
            lines.append("- none")
        return "\n".join(lines)

    @staticmethod
    def _normalize_anchor_profile(raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """归一化锚点配置，复用 OpenAI 兼容生成器的逻辑。"""
        return OpenAICompatibleInstrumentProfileGenerator._normalize_anchor_profile(raw, context)

    @staticmethod
    def _friendly_validation_error(exc: ValidationError) -> str:
        """生成友好的校验错误信息。"""
        return OpenAICompatibleInstrumentProfileGenerator._friendly_validation_error(exc)
