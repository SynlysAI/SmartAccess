"""DeepSeek-backed instrument profile draft generator."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract


class DeepSeekInstrumentProfileGenerator:
    """Generate reviewable instrument profiles with DeepSeek's chat API."""

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

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> InstrumentProfileContract:
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload)
            message = data["choices"][0]["message"]
            content = message["content"]
            reasoning = message.get("reasoning_content") or ""
            profile_data = self._extract_structured(content)
            self.last_reasoning = self._format_reasoning(reasoning, profile_data, prompt, context)
            return InstrumentProfileContract.model_validate(profile_data)
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## 生成失败\n\n```\n{exc}\n```"
            raise RuntimeError(f"DeepSeek 设备接入建议生成失败: {exc}") from exc

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "你是 SmartAccess 设备接入与校准助手。只输出一个 JSON 对象，不要 Markdown。\n"
            "JSON 必须严格符合 InstrumentProfileContract：\n"
            "{\n"
            '  "device_id": "...",\n'
            '  "supported_os": ["windows"],\n'
            '  "window_signature": {"title_contains": "...", "capture_width": 0, "capture_height": 0},\n'
            '  "anchors": [{"id": "anchor_id", "type": "button", "roi": {"x": 0, "y": 0, "width": 0, "height": 0}, "normalized_roi": {"x": 0, "y": 0, "width": 0, "height": 0}, "action_bindings": [{"action": "click", "requires_confirmation": false}], "vision_mode": "none"}],\n'
            '  "actions": ["click", "type", "hotkey", "wait_until"],\n'
            '  "safety_limits": {"requires_manual_confirm_for": [], "fields": []}\n'
            "}\n"
            "只能使用 context 中已有或用户明确描述的 ROI、动作和识别方式。"
            "如果缺少截图坐标，请输出少量建议锚点并把 ROI 设为 0 宽高，方便用户后续标注。"
            "不要自动保存，不要假设用户已经确认高风险动作。"
        )
        user = {
            "user_goal": prompt,
            "context": context,
            "required_profile": {
                "device_id": context.get("device_id") or "new_device",
                "title_contains": context.get("title_contains") or context.get("window_title") or "",
                "capture_width": context.get("capture_width"),
                "capture_height": context.get("capture_height"),
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
            with urlopen(request, timeout=self._timeout) as resp:  # noqa: S310 - user-configured LLM endpoint
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

    @staticmethod
    def _format_reasoning(reasoning: str, profile_data: dict[str, Any], prompt: str, context: dict[str, Any]) -> str:
        anchors = profile_data.get("anchors", []) if isinstance(profile_data, dict) else []
        lines = [
            "## 设备接入建议",
            f"**目标**：{prompt.strip()[:120] or '生成设备画像草稿'}",
            f"**窗口**：{context.get('title_contains') or context.get('window_title') or '-'}",
            "",
        ]
        if reasoning:
            lines += ["### 模型分析", reasoning.strip(), ""]
        lines.append("### 建议锚点")
        if anchors:
            for anchor in anchors:
                lines.append(
                    f"- `{anchor.get('id')}` · {anchor.get('type')} · {anchor.get('vision_mode', 'none')}"
                )
        else:
            lines.append("- 暂无建议锚点。")
        return "\n".join(lines)

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
