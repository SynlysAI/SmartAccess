"""OpenAI-compatible workflow and anchor-profile generators."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml
from pydantic import ValidationError

from smartaccess.shared.contracts.anchors import (
    ACTION_SUPPORT_SETS,
    SIMPLIFIED_ACTIONS,
    AnchorsContract,
)
from smartaccess.shared.contracts.workflow import WorkflowContract


DEFAULT_AI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class OpenAICompatibleChatClient:
    """Minimal OpenAI-compatible Chat Completions client."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "OpenAI-compatible",
        timeout_seconds: float = 30.0,
        user_agent: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._provider_name = provider_name
        self._timeout = timeout_seconds
        self._user_agent = (user_agent or DEFAULT_AI_USER_AGENT).strip() or DEFAULT_AI_USER_AGENT
        self.last_error = ""
        self.last_reasoning = ""

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def generator_label(self) -> str:
        return f"{self._provider_name} / {self._model}"

    def _request_config(self, context: dict[str, Any]) -> tuple[str, str, str]:
        base_url = str(context.get("ai_base_url") or self._base_url).rstrip("/")
        model = str(context.get("ai_model") or self._model)
        provider = str(context.get("ai_provider") or self._provider_name)
        return base_url, model, provider

    def _post(self, path: str, payload: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
        target_base_url = (base_url or self._base_url).rstrip("/")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{target_base_url}{path}",
            data=body,
            headers=self._headers(target_base_url),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as resp:  # noqa: S310 - user-configured LLM endpoint
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(self._format_http_error(exc.code, detail)) from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

    def _headers(self, target_base_url: str | None = None) -> dict[str, str]:
        base_url = (target_base_url or self._base_url).rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": self._user_agent,
        }
        origin = self._origin(base_url)
        if origin:
            headers["Origin"] = origin
            headers["Referer"] = f"{origin}/"
        return headers

    def _format_http_error(self, code: int, detail: str) -> str:
        parsed = self._parse_error_payload(detail)
        message = self._error_message(parsed) if parsed is not None else self._collapse(detail)
        combined = self._collapse(json.dumps(parsed, ensure_ascii=False) if parsed is not None else detail).lower()
        cloudflare_1010 = code == 403 and (
            "err_code" in combined and "1010" in combined
            or "error 1010" in combined
            or "browser's signature" in combined
            or "cloudflare" in combined and "1010" in combined
        )
        if cloudflare_1010:
            return (
                "HTTP 403 Cloudflare 1010: endpoint blocked this request signature. "
                f"Sent User-Agent={self._user_agent!r}. "
                "Set SMARTACCESS_AI_USER_AGENT in .env to a browser User-Agent allowed by the provider, "
                "or ask the provider to allow server-side API clients."
            )
        return f"HTTP {code}: {self._truncate(message)}"

    @staticmethod
    def _origin(base_url: str) -> str:
        parts = urlsplit(base_url)
        if not parts.scheme or not parts.netloc:
            return ""
        return f"{parts.scheme}://{parts.netloc}"

    @staticmethod
    def _parse_error_payload(detail: str) -> Any:
        try:
            return json.loads(detail)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _error_message(cls, payload: Any) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                parts = [
                    str(value)
                    for value in (
                        error.get("message"),
                        error.get("type"),
                        error.get("code"),
                    )
                    if value
                ]
                if parts:
                    return " | ".join(parts)
            parts = [
                str(value)
                for value in (
                    payload.get("title"),
                    payload.get("detail"),
                    payload.get("message"),
                    payload.get("err_code"),
                )
                if value
            ]
            if parts:
                return " | ".join(parts)
        return cls._collapse(json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _collapse(text: str) -> str:
        return " ".join(str(text).split())

    @staticmethod
    def _truncate(text: str, limit: int = 500) -> str:
        collapsed = OpenAICompatibleChatClient._collapse(text)
        if len(collapsed) <= limit:
            return collapsed
        return collapsed[: limit - 3].rstrip() + "..."

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
                raise ValueError("model output is not a JSON/YAML object")
            return data

    @staticmethod
    def _context_without_binary(context: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(context)
        screenshot = cleaned.pop("screenshot", None)
        if screenshot:
            cleaned["screenshot_attached"] = True
        return cleaned

    @staticmethod
    def _user_content(user_payload: dict[str, Any], context: dict[str, Any]) -> str | list[dict[str, Any]]:
        text = json.dumps(user_payload, ensure_ascii=False)
        screenshot = context.get("screenshot")
        if not isinstance(screenshot, dict) or not screenshot.get("data"):
            return text
        mime_type = str(screenshot.get("mime_type") or "image/png")
        data = str(screenshot["data"])
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{data}"}},
        ]

    @staticmethod
    def _message_content(data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if text:
                        parts.append(str(text))
                elif part:
                    parts.append(str(part))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _message_reasoning(data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]
        return str(message.get("reasoning_content") or "")


class OpenAICompatibleWorkflowGenerator(OpenAICompatibleChatClient):
    """Generate workflow drafts through an OpenAI-compatible chat endpoint."""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        self._normalization_notes: list[str] = []
        base_url, _model, _provider = self._request_config(context)
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload, base_url=base_url)
            workflow_data = self._extract_structured(self._message_content(data))
            workflow_data = self._normalize_wait_values(workflow_data)
            self.last_reasoning = self._format_reasoning(
                self._message_reasoning(data), workflow_data, prompt, context
            )
            return WorkflowContract.model_validate(workflow_data)
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n```\n{exc}\n```"
            raise RuntimeError(f"{self._provider_name} workflow generation failed: {exc}") from exc

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
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
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }

    @staticmethod
    def _format_reasoning(
        reasoning: str,
        workflow_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        lines = [
            "## Workflow draft",
            f"goal: {prompt.strip()[:120] or '-'}",
            f"anchor_profile: {context.get('anchor_profile') or context.get('instrument_profile') or '-'}",
            "",
        ]
        if reasoning:
            lines += ["### Model reasoning", reasoning.strip(), ""]
        lines.append("### Steps")
        for index, step in enumerate(workflow_data.get("steps", []) or [], 1):
            value = f" = {step.get('value')}" if step.get("value") is not None else ""
            lines.append(f"{index}. {step.get('id')} - {step.get('action')} -> {step.get('anchor_id')}{value}")
        return "\n".join(lines)

    def _normalize_wait_values(self, workflow_data: dict[str, Any]) -> dict[str, Any]:
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


class OpenAICompatibleInstrumentProfileGenerator(OpenAICompatibleChatClient):
    """Generate reviewable anchor profiles through an OpenAI-compatible chat endpoint."""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> AnchorsContract:
        base_url, _model, _provider = self._request_config(context)
        payload = self._chat_payload(prompt, context)
        try:
            data = self._post("/chat/completions", payload, base_url=base_url)
            profile_data = self._normalize_anchor_profile(
                self._extract_structured(self._message_content(data)),
                context,
            )
            self.last_reasoning = self._format_reasoning(
                self._message_reasoning(data), profile_data, prompt, context
            )
            return AnchorsContract.model_validate(profile_data)
        except ValidationError as exc:
            self.last_error = self._friendly_validation_error(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"AI anchor suggestion is not usable: {self.last_error}") from exc
        except Exception as exc:
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"{self._provider_name} anchor generation failed: {self.last_error}") from exc

    def _chat_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
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
        return {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": self._user_content(user, context)},
            ],
            "response_format": {"type": "json_object"},
        }

    @staticmethod
    def _format_reasoning(
        reasoning: str,
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
        ]
        if reasoning:
            lines += ["### Model reasoning", reasoning.strip(), ""]
        lines.append("### Suggested anchors")
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
                    OpenAICompatibleInstrumentProfileGenerator._normalize_anchor(anchor, width, height)
                )
        return normalized

    @staticmethod
    def _normalize_anchor(anchor: dict[str, Any], width: int | float, height: int | float) -> dict[str, Any]:
        action_region = anchor.get("action_region")
        if not action_region:
            pixel = anchor.get("roi") or {}
            normalized_roi = anchor.get("normalized_roi") or {}
            action_region = {
                "pixel": OpenAICompatibleInstrumentProfileGenerator._region(pixel),
                "normalized": OpenAICompatibleInstrumentProfileGenerator._normalized_region(
                    normalized_roi, pixel, width, height
                ),
            }
        observe_region = anchor.get("observe_region")
        observe_roi = anchor.get("observe_roi")
        if not observe_region and observe_roi:
            observe_region = {
                "pixel": OpenAICompatibleInstrumentProfileGenerator._region(observe_roi),
                "normalized": OpenAICompatibleInstrumentProfileGenerator._normalized_region(
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
        pixel_region = OpenAICompatibleInstrumentProfileGenerator._region(pixel)
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
            parts.append("缺少字段: " + ", ".join(missing[:8]))
        if invalid:
            parts.append("字段格式不正确: " + "; ".join(invalid[:4]))
        parts.append("请继续手动标注锚点 ROI，或让 AI 只给出锚点名称建议。")
        return "\n".join(parts)
