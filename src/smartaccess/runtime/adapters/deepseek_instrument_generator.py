"""DeepSeek-backed anchor profile draft generator."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml
from pydantic import ValidationError

from smartaccess.shared.contracts.anchors import (
    ACTION_SUPPORT_SETS,
    SIMPLIFIED_ACTIONS,
    AnchorsContract,
)


class DeepSeekInstrumentProfileGenerator:
    """Generate reviewable anchor profiles with DeepSeek's chat API."""

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

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> AnchorsContract:
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload)
            message = data["choices"][0]["message"]
            content = message["content"]
            reasoning = message.get("reasoning_content") or ""
            profile_data = self._normalize_anchor_profile(
                self._extract_structured(content),
                context,
            )
            self.last_reasoning = self._format_reasoning(reasoning, profile_data, prompt, context)
            return AnchorsContract.model_validate(profile_data)
        except ValidationError as exc:
            self.last_error = self._friendly_validation_error(exc)
            self.last_reasoning = f"## 生成失败\n\n{self.last_error}"
            raise RuntimeError(f"AI 辅助接入建议不可用：{self.last_error}") from exc
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## 生成失败\n\n{self.last_error}"
            raise RuntimeError(f"AI 辅助接入建议生成失败：{self.last_error}") from exc

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "你是 SmartAccess 设备接入与校准助手。只输出一个 JSON 对象，不要 Markdown。\n"
            "JSON 必须符合 anchors.yaml 简化锚点模型：\n"
            "{\n"
            '  "profile_id": "...",\n'
            '  "window_signature": {"title_contains": "...", "screenshot_size": {"width": 0, "height": 0}},\n'
            '  "anchors": [{"id": "anchor_id", "action_region": {"pixel": {"x": 0, "y": 0, "width": 0, "height": 0}, "normalized": {"x": 0, "y": 0, "width": 0, "height": 0}}, "observe_region": null, "supported_actions": ["click"], "default_wait_seconds": 2.0, "action_bindings": [{"action": "click", "requires_confirmation": false}]}]\n'
            "}\n"
            "动作只能是 click、type、hotkey、press_enter。"
            "一个锚点包含一个动作区域，可选一个 OCR 观察区域 observe_region。"
            "不要输出 workflow 字段、outputs、roi_bindings、wait、wait_until、double_click。"
            "如果缺少截图坐标，请输出少量建议锚点并把区域设为 0 宽高，方便用户后续标注。"
            "不要自动保存，不要假设用户已经确认高风险动作。"
        )
        user = {
            "user_goal": prompt,
            "context": context,
            "required_profile": {
                "profile_id": context.get("device_id") or "new_device",
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
    def _format_reasoning(
        reasoning: str,
        profile_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        anchors = profile_data.get("anchors", []) if isinstance(profile_data, dict) else []
        lines = [
            "## 设备接入建议",
            f"**目标**：{prompt.strip()[:120] or '生成设备画像草稿'}",
            f"**窗口**：{context.get('title_contains') or context.get('window_title') or '-'}",
            "",
            "### 结构化依据",
            "- 输出契约：anchors.yaml / AnchorsContract",
            "- 高风险动作：写入锚点 action_bindings.requires_confirmation",
            "- 待补 ROI：宽高为 0 的建议锚点需人工拖拽标注",
            "",
        ]
        if reasoning:
            lines += ["### 模型摘要", reasoning.strip(), ""]
        lines.append("### 建议锚点")
        if anchors:
            for anchor in anchors:
                has_action = bool(anchor.get("action_region"))
                has_observe = bool(anchor.get("observe_region"))
                actions = ", ".join(anchor.get("supported_actions") or [])
                lines.append(
                    f"- `{anchor.get('id')}` · action_region={has_action} · observe_region={has_observe} · actions={actions or 'click'}"
                )
        else:
            lines.append("- 暂无建议锚点。")
        return "\n".join(lines)

    @staticmethod
    def _normalize_anchor_profile(raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        data = dict(raw)
        profile_id = data.get("profile_id") or data.get("device_id") or context.get("device_id") or "new_device"
        window_signature = dict(data.get("window_signature") or {})
        screenshot_size = dict(window_signature.get("screenshot_size") or {})
        width = screenshot_size.get("width") or window_signature.get("capture_width") or context.get("capture_width") or 0
        height = screenshot_size.get("height") or window_signature.get("capture_height") or context.get("capture_height") or 0
        normalized = {
            "profile_id": profile_id,
            "window_signature": {
                "title_contains": (
                    window_signature.get("title_contains")
                    or context.get("title_contains")
                    or context.get("window_title")
                    or ""
                ),
                "screenshot_size": {"width": width, "height": height},
            },
            "anchors": [],
            "supported_os": data.get("supported_os") or ["windows"],
            "safety_limits": data.get("safety_limits") or {"requires_manual_confirm_for": [], "fields": []},
        }
        for anchor in data.get("anchors") or []:
            if isinstance(anchor, dict):
                normalized["anchors"].append(
                    DeepSeekInstrumentProfileGenerator._normalize_anchor(anchor, width, height)
                )
        return normalized

    @staticmethod
    def _normalize_anchor(anchor: dict[str, Any], width: int | float, height: int | float) -> dict[str, Any]:
        action_region = anchor.get("action_region")
        if not action_region:
            pixel = anchor.get("roi") or {}
            normalized_roi = anchor.get("normalized_roi") or {}
            action_region = {
                "pixel": DeepSeekInstrumentProfileGenerator._region(pixel),
                "normalized": DeepSeekInstrumentProfileGenerator._normalized_region(
                    normalized_roi, pixel, width, height
                ),
            }
        observe_region = anchor.get("observe_region")
        observe_roi = anchor.get("observe_roi")
        if not observe_region and observe_roi:
            observe_region = {
                "pixel": DeepSeekInstrumentProfileGenerator._region(observe_roi),
                "normalized": DeepSeekInstrumentProfileGenerator._normalized_region(
                    anchor.get("observe_normalized_roi") or {}, observe_roi, width, height
                ),
            }
        actions = [
            str(action)
            for action in (anchor.get("supported_actions") or [])
            if str(action) in SIMPLIFIED_ACTIONS
        ]
        bindings = [
            binding
            for binding in (anchor.get("action_bindings") or [])
            if isinstance(binding, dict) and str(binding.get("action")) in SIMPLIFIED_ACTIONS
        ]
        if not actions and bindings:
            actions = [str(binding["action"]) for binding in bindings]
        if not actions:
            main_action = str(anchor.get("main_action") or (bindings[0].get("action") if bindings else "click"))
            actions = ACTION_SUPPORT_SETS.get(main_action, ["click"])
        actions = list(dict.fromkeys(actions))
        confirm = any(bool(binding.get("requires_confirmation")) for binding in bindings)
        return {
            "id": anchor.get("id") or "anchor",
            "action_region": action_region,
            "observe_region": observe_region,
            "supported_actions": actions,
            "default_wait_seconds": float(anchor.get("default_wait_seconds") or 2.0),
            "notes": anchor.get("notes"),
            "action_bindings": [
                {"action": action, "requires_confirmation": confirm}
                for action in actions
            ],
        }

    @staticmethod
    def _region(raw: dict[str, Any] | None) -> dict[str, float]:
        raw = raw or {}
        if "pixel" in raw and isinstance(raw["pixel"], dict):
            raw = raw["pixel"]
        return {
            "x": float(raw.get("x") or 0),
            "y": float(raw.get("y") or 0),
            "width": float(raw.get("width") or 0),
            "height": float(raw.get("height") or 0),
        }

    @staticmethod
    def _normalized_region(
        normalized: dict[str, Any] | None,
        pixel: dict[str, Any] | None,
        width: int | float,
        height: int | float,
    ) -> dict[str, float]:
        normalized = normalized or {}
        if "normalized" in normalized and isinstance(normalized["normalized"], dict):
            normalized = normalized["normalized"]
        if normalized:
            return {
                "x": float(normalized.get("x") or 0),
                "y": float(normalized.get("y") or 0),
                "width": float(normalized.get("width") or 0),
                "height": float(normalized.get("height") or 0),
            }
        pixel_region = DeepSeekInstrumentProfileGenerator._region(pixel)
        return {
            "x": min(1.0, pixel_region["x"] / width) if width else 0.0,
            "y": min(1.0, pixel_region["y"] / height) if height else 0.0,
            "width": min(1.0, pixel_region["width"] / width) if width else 0.0,
            "height": min(1.0, pixel_region["height"] / height) if height else 0.0,
        }

    @staticmethod
    def _friendly_validation_error(exc: ValidationError) -> str:
        missing = []
        invalid = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", ()))
            if error.get("type") == "missing":
                missing.append(loc)
            else:
                invalid.append(f"{loc}: {error.get('msg')}")
        parts = []
        if missing:
            parts.append("缺少字段：" + "、".join(missing[:8]))
        if invalid:
            parts.append("字段格式不正确：" + "；".join(invalid[:4]))
        parts.append("请继续手动标注锚点 ROI，或让 AI 只给出锚点名称建议。")
        return "\n".join(parts)

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
