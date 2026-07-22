"""DeepSeek Chat 与 Codex Responses 的统一 AI 生成器。"""

from __future__ import annotations

import json
import re
import socket
import ssl
from http.client import RemoteDisconnected
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml
from pydantic import ValidationError

try:  # pragma: no cover - optional dependency in packaged builds
    import certifi
except Exception:  # noqa: BLE001
    certifi = None  # type: ignore[assignment]

from smartaccess.shared.config.settings import DEFAULT_AI_USER_AGENT
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.workflow import (
    DEFAULT_ACTION_WAIT_SECONDS,
    DEFAULT_OCR_POLL_INTERVAL_SECONDS,
    DEFAULT_OCR_TIMEOUT_SECONDS,
    WorkflowContract,
)

CODEX_USER_AGENT = (
    "codex_vscode/0.137.0-alpha.4 "
    "(Windows 10.0.26200; x86_64) unknown (VS Code; 26.602.71036)"
)
CODEX_WORKFLOW_DRAFT_MIN_TIMEOUT_SECONDS = 120.0
IMAGE_DRAFT_MIN_TIMEOUT_SECONDS = 120.0


class SmartAccessAiGenerator:
    """根据 provider 自动选择 Chat 或 Responses 接口生成草稿。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider: str,
        timeout_seconds: float = 30.0,
        user_agent: str | None = None,
        enable_thinking: bool = False,
        default_action_wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
        default_ocr_timeout_seconds: float = DEFAULT_OCR_TIMEOUT_SECONDS,
        default_ocr_poll_interval_seconds: float = DEFAULT_OCR_POLL_INTERVAL_SECONDS,
        default_precheck_image_threshold: float = 0.8,
    ) -> None:
        """初始化 AI 生成器。

        Args:
            api_key: API Key。
            base_url: API 基础地址。
            model: 模型名称。
            provider: AI 提供者名称。
            timeout_seconds: 请求超时时间。
            user_agent: 可选 User-Agent。
            enable_thinking: 是否启用模型思考模式。
            default_action_wait_seconds: 默认动作后等待秒数。
            default_ocr_timeout_seconds: 默认 OCR 超时秒数。
            default_ocr_poll_interval_seconds: 默认 OCR 轮询间隔秒数。
            default_precheck_image_threshold: 默认执行前图像相似度阈值。
        """

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._provider = provider.lower().strip() or "deepseek"
        self._timeout = timeout_seconds
        self._user_agent = (
            CODEX_USER_AGENT
            if self._provider == "codex"
            else (user_agent or DEFAULT_AI_USER_AGENT)
        )
        self._enable_thinking = enable_thinking
        self._default_action_wait_seconds = default_action_wait_seconds
        self._default_ocr_timeout_seconds = default_ocr_timeout_seconds
        self._default_ocr_poll_interval_seconds = default_ocr_poll_interval_seconds
        self._default_precheck_image_threshold = default_precheck_image_threshold
        self.last_error = ""
        self.last_reasoning = ""

    @property
    def supports_images(self) -> bool:
        """返回当前 provider 是否支持发送截图。"""

        return self._provider == "codex" or self._provider == "qwen"

    def generator_label(self) -> str:
        """返回生成器标签。"""

        mode = "Responses" if self._provider == "codex" else "Chat"
        vision = "vision" if self.supports_images else "text-only"
        return f"{self._provider} / {self._model} / {mode} / {vision}"

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> Any:
        """兼容 WorkflowDraftGenerator 协议的工作流生成入口。"""

        return self.draft_workflow(prompt, context)

    def draft_workflow(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> WorkflowContract:
        """根据文本和锚点上下文生成工作流草稿。

        Args:
            prompt: 用户描述。
            context: 工作流生成上下文。

        Returns:
            工作流契约。
        """

        payload = self._workflow_payload(prompt, context)
        try:
            timeout_seconds = (
                max(self._timeout, CODEX_WORKFLOW_DRAFT_MIN_TIMEOUT_SECONDS)
                if self._provider == "codex"
                else self._timeout
            )
            content = self._send(payload, timeout_seconds=timeout_seconds)
            workflow_data = self._normalize_workflow(
                self._extract_structured(content),
                default_action_wait_seconds=self._default_action_wait_seconds,
                default_ocr_timeout_seconds=self._default_ocr_timeout_seconds,
                default_ocr_poll_interval_seconds=(
                    self._default_ocr_poll_interval_seconds
                ),
            )
            self.last_reasoning = self._workflow_reasoning(workflow_data, prompt, context)
            return WorkflowContract.model_validate(workflow_data)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n```\n{exc}\n```"
            raise RuntimeError(f"{self._provider} 工作流生成失败: {exc}") from exc

    def draft_instrument_profile(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> AnchorsContract:
        """根据窗口截图和描述生成设备锚点草稿。

        Args:
            prompt: 用户描述。
            context: 设备接入上下文。

        Returns:
            锚点配置契约。
        """

        payload = self._instrument_payload(prompt, context)
        try:
            has_image = bool(
                self.supports_images
                and isinstance(context.get("screenshot"), dict)
                and context["screenshot"].get("data")
            )
            timeout_seconds = (
                max(self._timeout, IMAGE_DRAFT_MIN_TIMEOUT_SECONDS)
                if has_image
                else self._timeout
            )
            content = self._send(payload, timeout_seconds=timeout_seconds)
            profile_data = self._normalize_anchor_profile(
                self._extract_structured(content),
                context,
                default_precheck_image_threshold=(
                    self._default_precheck_image_threshold
                ),
            )
            self.last_reasoning = self._instrument_reasoning(profile_data, prompt, context)
            return AnchorsContract.model_validate(profile_data)
        except ValidationError as exc:
            self.last_error = self._friendly_validation_error(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"AI 锚点建议不可用: {self.last_error}") from exc
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.last_reasoning = f"## Generation failed\n\n{self.last_error}"
            raise RuntimeError(f"{self._provider} 设备接入生成失败: {exc}") from exc

    def _send(
        self,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> str:
        """按 provider 发送请求并返回文本内容。"""

        if self._provider == "codex":
            data = self._post("/responses", payload, timeout_seconds=timeout_seconds)
            return self._responses_content(data)
        data = self._post("/chat/completions", payload, timeout_seconds=timeout_seconds)
        return self._chat_content(data)

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """发送 JSON POST 请求。"""

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self._base_url}{path}"
        request_timeout = timeout_seconds or self._timeout
        last_error: Exception | None = None
        for attempt in range(2):
            request = Request(
                url,
                data=body,
                headers=self._headers(),
                method="POST",
            )
            try:
                kwargs: dict[str, Any] = {"timeout": request_timeout}
                context = self._https_context()
                if context is not None and urlsplit(url).scheme == "https":
                    kwargs["context"] = context
                with urlopen(request, **kwargs) as response:  # noqa: S310
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(self._format_http_error(exc.code, detail)) from exc
            except TimeoutError as exc:
                raise RuntimeError(self._format_timeout_error(request_timeout)) from exc
            except socket.timeout as exc:
                raise RuntimeError(self._format_timeout_error(request_timeout)) from exc
            except ssl.SSLError as exc:
                raise RuntimeError(self._format_transport_error(exc)) from exc
            except URLError as exc:
                if attempt == 0 and self._should_retry_transport_error(exc.reason):
                    last_error = exc
                    continue
                raise RuntimeError(self._format_transport_error(exc.reason)) from exc
            except OSError as exc:
                if attempt == 0 and self._should_retry_transport_error(exc):
                    last_error = exc
                    continue
                raise RuntimeError(self._format_transport_error(exc)) from exc
        if last_error is not None:  # pragma: no cover - defensive
            raise RuntimeError(self._format_transport_error(last_error)) from last_error
        raise RuntimeError(self._format_transport_error("request failed"))

    def _headers(self) -> dict[str, str]:
        """构建请求头。"""

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if self._provider != "codex":
            origin = self._origin(self._base_url)
            if origin:
                headers["Origin"] = origin
                headers["Referer"] = f"{origin}/"
            headers["Accept-Language"] = "en-US,en;q=0.9"
        return headers

    def _workflow_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """构建工作流生成请求。"""

        system = (
            "You are the SmartAccess workflow designer. Return only one JSON object, "
            "no Markdown.\n"
            "The JSON must match this simplified WorkflowContract shape:\n"
            '{"metadata":{"workflow_id":"...","author":"ai-assistant",'
            '"anchor_profile":"...","experiment_type":"...",'
            '"lifecycle_state":"Draft"},'
            '"preconditions":[{"description":"..."}],'
            '"steps":[{"id":"step_1",'
            '"action":"click","view_id":"main","anchor_id":"anchor_id","value":null,'
            f'"wait_seconds":{self._default_action_wait_seconds:g},'
            '"match_mode":"none","requires_confirmation":false},'
            '{"id":"step_2","action":"ocr","view_id":"main",'
            '"anchor_id":"status_anchor","match_mode":"contains",'
            '"expected_text":"ready",'
            f'"timeout_seconds":{self._default_ocr_timeout_seconds:g},'
            f'"poll_interval_seconds":{self._default_ocr_poll_interval_seconds:g},'
            f'"wait_seconds":{self._default_action_wait_seconds:g}}},'
            '{"id":"step_3","action":"type","view_id":"main",'
            '"anchor_id":"anchor_id","value":null,"input_mode":"incrementing",'
            '"increment_rule":{"pattern":"{device_id}-{date}-{counter:03d}",'
            '"sequence_key":"sample_id","date_format":"%Y%m%d",'
            '"start":1,"width":3},"match_mode":"none"}],'
            '"retry_policy":{"max_attempts":2}}\n'
            "preconditions must be an array of objects, never an array of strings.\n"
            "match_mode must be one of contains, equals, regex, not_empty, none; "
            "never use exact.\n"
            "input_mode must be one of free, incrementing; never use replace or other values.\n"
            "Allowed actions: click, type, hotkey, press_enter, ocr, wait.\n"
            "For action=ocr, the anchor's action_region is the OCR scan area; "
            "set match_mode and expected_text for OCR conditions. "
            f"timeout_seconds defaults to {self._default_ocr_timeout_seconds:g} "
            "seconds and poll_interval_seconds defaults to "
            f"{self._default_ocr_poll_interval_seconds:g} seconds.\n"
            "For action=wait, omit anchor_id and set wait_seconds.\n"
            "For all non-wait actions, wait_seconds is the delay after the step succeeds; "
            f"default to {self._default_action_wait_seconds:g} seconds, and 0 means "
            "no delay.\n"
            "Never place OCR match fields on click, type, hotkey, press_enter, or wait steps. "
            "Insert a separate action=ocr step immediately after the action that needs checking.\n"
            "Use requires_confirmation=true only when that exact step must ask for human "
            "confirmation before execution. Do not create standalone manual-confirm wait steps.\n"
            "All wait_seconds, timeout_seconds, and poll_interval_seconds values "
            "are seconds.\n"
            "Use only calibrated anchors, view_id values, and actions from context."
        )
        user = {
            "user_prompt": prompt,
            "context": self._context_for_provider(context),
            "required_metadata": {
                "workflow_id": context.get("workflow_id", "wf_ai_draft"),
                "anchor_profile": context.get("anchor_profile")
                or context.get("instrument_profile")
                or "unknown_device",
                "experiment_type": context.get("experiment_type", "generic_automation"),
                "author": "ai-assistant",
                "lifecycle_state": "Draft",
            },
        }
        return self._build_payload(system, json.dumps(user, ensure_ascii=False), context)

    def _instrument_payload(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """构建设备接入生成请求。"""

        system = (
            "你是 SmartAccess 的设备接入与界面校准助手。请基于用户目标、上下文和附带的"
            "原始截图，生成可供用户复核的锚点初稿。只返回一个 JSON 对象，禁止 Markdown、"
            "解释文字或代码围栏。\n"
            "JSON 必须匹配以下简化 anchors.yaml 结构：\n"
            '{"profile_id":"...","window_signature":{"title_contains":"...",'
            '"screenshot_size":{"width":0,"height":0}},"views":[{"view_id":"main",'
            '"window_signature":{"title_contains":"..."},"screenshot_size":{"width":0,"height":0},'
            '"anchors":[{"id":"anchor_id",'
            '"action_region":{"pixel":{"x":0,"y":0,"width":0,"height":0},'
            '"normalized":{"x":0,"y":0,"width":0,"height":0}}}]}]}\n'
            "锚点只描述界面位置，不包含工作流动作或人工确认配置。每个锚点恰好包含一个"
            "action_region，供后续工作流点击、输入或识别使用。\n"
            "坐标规则（必须严格遵守）：\n"
            "1. 所有 pixel 坐标以附带原始截图左上角为 (0, 0)，不是屏幕坐标、窗口坐标，"
            "也不是页面缩放后的显示坐标。\n"
            "2. pixel.x、pixel.y、pixel.width、pixel.height 必须是非负整数；width 和 height"
            " 必须大于 0；区域必须完全落在截图宽高范围内。\n"
            "3. normalized 必须由同一截图尺寸精确换算：x / screenshot_width、"
            "y / screenshot_height、width / screenshot_width、height / screenshot_height，"
            "并保留 6 位以内小数。\n"
            "4. action_region 应紧密覆盖可点击控件、输入框或待识别文本，允许保留少量边距，"
            "不得使用整行、整块面板或整个窗口代替具体控件。\n"
            "锚点选择规则：\n"
            "1. 只生成用户目标明确需要控制或识别的元素；不要为了凑数量识别无关图标、"
            "装饰、聊天内容或不相关窗口。\n"
            "2. id 使用稳定、语义清晰的英文 snake_case，例如 save_button、"
            "username_input、connection_status。不要使用 anchor_1、button1 等泛化名称。\n"
            "3. 只有在截图中能可靠定位时才输出锚点；无法看清、被遮挡、截图未附带或坐标"
            "不确定时，直接省略该锚点，绝不能输出零尺寸、猜测坐标或越界坐标。\n"
            "4. 默认不要输出 precheck，除非用户明确要求为某个锚点配置执行前校验。需要"
            "校验时，默认将 precheck.region 的 pixel 和 normalized 完整复制 action_region；"
            "只有用户明确要求校验其他稳定区域时，才使用不同的自定义校验区域。\n"
            "5. precheck 可选结构为：{\"mode\":\"image\"|\"text\"|\"image_text\","
            "\"region\":{\"pixel\":{...},\"normalized\":{...}},\"image_threshold\":"
            f"{self._default_precheck_image_threshold:g}" + "}。按钮和图标使用 image；只有校验"
            "区域包含稳定、清晰、可读文字时才使用 text 或 image_text。\n"
            "6. 若无法可靠定位任何元素，返回 anchors 为空数组，同时保留正确的 profile_id、"
            "窗口标题和截图尺寸。\n"
            "输出前自行检查：JSON 可解析；所有 id 唯一；每个区域非零且未越界；pixel 与"
            "normalized 坐标一致；截图尺寸必须使用上下文提供的 capture_width 和 capture_height。"
        )
        user = {
            "user_goal": prompt,
            "context": self._context_for_provider(context),
            "required_profile": {
                "profile_id": context.get("device_id") or "new_device",
                "title_contains": context.get("title_contains")
                or context.get("window_title")
                or "",
                "capture_width": context.get("capture_width"),
                "capture_height": context.get("capture_height"),
                "image_attached": bool(
                    self.supports_images
                    and isinstance(context.get("screenshot"), dict)
                    and context["screenshot"].get("data")
                ),
            },
        }
        return self._build_payload(system, json.dumps(user, ensure_ascii=False), context)

    def _build_payload(
        self,
        system: str,
        user_text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """按接口类型构建请求体。"""

        if self._provider == "codex":
            return {
                "model": self._model,
                "temperature": 0.2,
                "input": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": self._responses_user_content(user_text, context),
                    },
                ],
            }
        return {
            "model": self._model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": self._chat_user_content(user_text, context)},
            ],
            "response_format": {"type": "json_object"},
            **self._chat_generation_options(),
        }

    def _responses_user_content(
        self,
        user_text: str,
        context: dict[str, Any],
    ) -> str | list[dict[str, Any]]:
        """构建 Responses 用户内容，Codex 可携带图片。"""

        screenshot = context.get("screenshot")
        if not self.supports_images or not isinstance(screenshot, dict):
            return user_text
        if not screenshot.get("data"):
            return user_text
        mime_type = str(screenshot.get("mime_type") or "image/png")
        return [
            {"type": "input_text", "text": user_text},
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{screenshot['data']}",
            },
        ]

    def _chat_user_content(
        self,
        user_text: str,
        context: dict[str, Any],
    ) -> str | list[dict[str, Any]]:
        """构建 Chat Completions 用户内容，Chat 视觉模型可携带图片。

        Args:
            user_text: 用户文本内容。
            context: 生成上下文。

        Returns:
            文本或 OpenAI 兼容的多模态 content 列表。
        """

        screenshot = context.get("screenshot")
        if self._provider != "qwen":
            return user_text
        if not isinstance(screenshot, dict) or not screenshot.get("data"):
            return user_text
        mime_type = str(screenshot.get("mime_type") or "image/png")
        return [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{screenshot['data']}",
                },
            },
        ]

    def _chat_generation_options(self) -> dict[str, Any]:
        """返回 Chat 视觉模型的固定生成参数。"""

        if self._provider != "qwen":
            return {}
        return {
            "chat_template_kwargs": {"enable_thinking": self._enable_thinking},
        }

    def _context_for_provider(self, context: dict[str, Any]) -> dict[str, Any]:
        """返回适配当前 provider 能力的上下文。"""

        cleaned = dict(context)
        screenshot = cleaned.pop("screenshot", None)
        cleaned["screenshot_attached"] = bool(
            self.supports_images
            and isinstance(screenshot, dict)
            and screenshot.get("data")
        )
        if not self.supports_images and screenshot:
            cleaned["screenshot_omitted_reason"] = "provider_does_not_support_images"
        return cleaned

    @staticmethod
    def _chat_content(data: dict[str, Any]) -> str:
        """从 Chat Completions 响应提取文本。"""

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        if isinstance(content, list):
            return "\n".join(str(item.get("text") or item) for item in content)
        return str(content)

    @staticmethod
    def _responses_content(data: dict[str, Any]) -> str:
        """从 Responses API 响应提取文本。"""

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
    def _extract_structured(content: str) -> dict[str, Any]:
        """从模型输出中提取 JSON/YAML 对象。"""

        stripped = SmartAccessAiGenerator._strip_thinking_content(content).strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith(("json", "yaml")):
                stripped = stripped.split("\n", 1)[1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            data = yaml.safe_load(stripped)
            if not isinstance(data, dict):
                raise ValueError("model output is not a JSON/YAML object")
            return data

    @staticmethod
    def _strip_thinking_content(content: str) -> str:
        """移除模型输出中的思考内容，仅保留最终回答。

        Args:
            content: 模型原始输出文本。

        Returns:
            去除 `<think>` 片段后的文本。
        """

        stripped = content.strip()
        stripped = re.sub(r"<think>.*?</think>", "", stripped, flags=re.DOTALL).strip()
        if "</think>" in stripped:
            stripped = stripped.split("</think>", 1)[1].strip()
        return stripped

    @staticmethod
    def _normalize_workflow(
        workflow_data: dict[str, Any],
        *,
        default_action_wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
        default_ocr_timeout_seconds: float = DEFAULT_OCR_TIMEOUT_SECONDS,
        default_ocr_poll_interval_seconds: float = DEFAULT_OCR_POLL_INTERVAL_SECONDS,
    ) -> dict[str, Any]:
        """归一化工作流草稿字段。

        Args:
            workflow_data: AI 返回的工作流数据。
            default_action_wait_seconds: 默认动作后等待秒数。
            default_ocr_timeout_seconds: 默认 OCR 超时秒数。
            default_ocr_poll_interval_seconds: 默认 OCR 轮询间隔秒数。

        Returns:
            标准化后的工作流数据。
        """

        workflow_data.pop("roi_bindings", None)
        workflow_data.pop("outputs", None)
        workflow_data["preconditions"] = SmartAccessAiGenerator._normalize_preconditions(
            workflow_data.get("preconditions")
        )
        for step in workflow_data.get("steps", []) or []:
            if "anchor_id" not in step and step.get("target"):
                step["anchor_id"] = step.get("target")
            if not step.get("view_id"):
                step["view_id"] = "main"
            action = step.get("action")
            if action == "wait":
                step.pop("anchor_id", None)
                step.pop("target", None)
                step["view_id"] = "main"
                step["match_mode"] = "none"
                step.pop("expected_text", None)
                step.pop("expected_candidates", None)
                step.pop("timeout_seconds", None)
                step.pop("poll_interval_seconds", None)
                if step.get("wait_seconds") is None and step.get("value") is not None:
                    step["wait_seconds"] = SmartAccessAiGenerator._seconds(step["value"])
                if step.get("wait_seconds") is None:
                    step["wait_seconds"] = default_action_wait_seconds
            if action == "ocr":
                if step.get("match_mode") in (None, "none"):
                    step["match_mode"] = "not_empty"
                if step.get("timeout_seconds") is None:
                    step["timeout_seconds"] = default_ocr_timeout_seconds
                if step.get("poll_interval_seconds") is None:
                    step["poll_interval_seconds"] = (
                        default_ocr_poll_interval_seconds
                    )
                step.pop("ignore_case", None)
                step.pop("normalize_text", None)
                step.pop("min_confidence", None)
            elif action != "wait":
                step["match_mode"] = "none"
                step.pop("expected_text", None)
                step.pop("expected_candidates", None)
                step.pop("timeout_seconds", None)
                step.pop("poll_interval_seconds", None)
                step.pop("min_confidence", None)
                step.pop("ignore_case", None)
                step.pop("normalize_text", None)
            if action != "wait" and step.get("wait_seconds") is None:
                step["wait_seconds"] = default_action_wait_seconds
            for field in (
                "wait_seconds",
                "timeout_seconds",
                "poll_interval_seconds",
            ):
                if step.get(field) is not None:
                    step[field] = SmartAccessAiGenerator._seconds(step[field])
            if step.get("input_mode") not in ("free", "incrementing"):
                step["input_mode"] = "free"
        return workflow_data

    @staticmethod
    def _normalize_preconditions(raw: Any) -> list[dict[str, Any]]:
        """Return audit-friendly preconditions as contract objects."""

        if raw is None:
            return []
        if not isinstance(raw, list):
            raw = [raw]
        preconditions: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                preconditions.append(item)
                continue
            if item is None:
                continue
            text = str(item).strip()
            if text:
                preconditions.append({"description": text})
        return preconditions

    @staticmethod
    def _normalize_anchor_profile(
        raw: dict[str, Any],
        context: dict[str, Any],
        *,
        default_precheck_image_threshold: float = 0.8,
    ) -> dict[str, Any]:
        """归一化锚点配置草稿。

        Args:
            raw: AI 返回的锚点配置数据。
            context: AI 辅助接入上下文。
            default_precheck_image_threshold: 默认图像相似度阈值。

        Returns:
            标准化后的锚点配置数据。
        """

        data = dict(raw)
        window_signature = dict(data.get("window_signature") or {})
        screenshot_size = dict(window_signature.get("screenshot_size") or {})
        width = (
            screenshot_size.get("width")
            or window_signature.get("capture_width")
            or context.get("capture_width")
            or 0
        )
        height = (
            screenshot_size.get("height")
            or window_signature.get("capture_height")
            or context.get("capture_height")
            or 0
        )
        normalized = {
            "profile_id": data.get("profile_id")
            or data.get("device_id")
            or context.get("device_id")
            or "new_device",
            "window_signature": {
                "title_contains": window_signature.get("title_contains")
                or context.get("title_contains")
                or context.get("window_title")
                or "",
                "screenshot_size": {"width": width, "height": height},
            },
            "anchors": [],
            "views": [],
            "supported_os": data.get("supported_os") or ["windows"],
            "safety_limits": data.get("safety_limits") or {},
        }
        raw_views = data.get("views") or []
        if raw_views:
            for view in raw_views:
                if not isinstance(view, dict):
                    continue
                view_signature = dict(view.get("window_signature") or {})
                view_size = dict(view.get("screenshot_size") or view_signature.get("screenshot_size") or {})
                view_width = view_size.get("width") or width
                view_height = view_size.get("height") or height
                view_anchors = [
                    SmartAccessAiGenerator._normalize_anchor(
                        anchor,
                        view_width,
                        view_height,
                        default_precheck_image_threshold=(
                            default_precheck_image_threshold
                        ),
                    )
                    for anchor in (view.get("anchors") or [])
                    if isinstance(anchor, dict)
                ]
                normalized["views"].append(
                    {
                        "view_id": view.get("view_id") or "main",
                        "window_signature": {
                            "title_contains": view_signature.get("title_contains")
                            or normalized["window_signature"]["title_contains"],
                            "screenshot_size": {
                                "width": view_width,
                                "height": view_height,
                            },
                        },
                        "screenshot_size": {"width": view_width, "height": view_height},
                        "anchors": view_anchors,
                        "capture_asset_path": view.get("capture_asset_path"),
                    }
                )
                normalized["anchors"].extend(view_anchors)
        else:
            for anchor in data.get("anchors") or []:
                if isinstance(anchor, dict):
                    normalized["anchors"].append(
                        SmartAccessAiGenerator._normalize_anchor(
                            anchor,
                            width,
                            height,
                            default_precheck_image_threshold=(
                                default_precheck_image_threshold
                            ),
                        )
                    )
        if not normalized["views"]:
            normalized["views"].append(
                {
                    "view_id": "main",
                    "window_signature": normalized["window_signature"],
                    "screenshot_size": {"width": width, "height": height},
                    "anchors": list(normalized["anchors"]),
                    "capture_asset_path": "capture.png",
                }
            )
        return normalized

    @staticmethod
    def _normalize_anchor(
        anchor: dict[str, Any],
        width: int | float,
        height: int | float,
        *,
        default_precheck_image_threshold: float = 0.8,
    ) -> dict[str, Any]:
        """归一化单个锚点草稿。

        Args:
            anchor: AI 返回的单个锚点数据。
            width: 校准截图宽度。
            height: 校准截图高度。
            default_precheck_image_threshold: 默认图像相似度阈值。

        Returns:
            标准化后的锚点数据。
        """

        action_region = anchor.get("action_region")
        if not action_region:
            pixel = anchor.get("roi") or {}
            action_region = {
                "pixel": SmartAccessAiGenerator._region(pixel),
                "normalized": SmartAccessAiGenerator._normalized_region(
                    anchor.get("normalized_roi") or {},
                    pixel,
                    width,
                    height,
                ),
            }
        precheck = anchor.get("precheck")
        normalized_precheck = None
        if isinstance(precheck, dict):
            mode = str(precheck.get("mode") or "").strip()
            region = precheck.get("region")
            if mode in {"image", "text", "image_text"} and isinstance(region, dict):
                pixel = region.get("pixel") or {}
                normalized_precheck = {
                    "mode": mode,
                    "region": {
                        "pixel": SmartAccessAiGenerator._region(pixel),
                        "normalized": SmartAccessAiGenerator._normalized_region(
                            region.get("normalized") or {},
                            pixel,
                            width,
                            height,
                        ),
                    },
                    "image_threshold": float(
                        precheck.get("image_threshold")
                        if precheck.get("image_threshold") is not None
                        else default_precheck_image_threshold
                    ),
                }
        return {
            "id": anchor.get("id") or "anchor",
            "action_region": action_region,
            "precheck": normalized_precheck,
            "notes": anchor.get("notes"),
        }

    @staticmethod
    def _region(raw: dict[str, Any] | None) -> dict[str, float]:
        """提取像素区域。"""

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
        """提取或计算归一化区域。"""

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
        pixel_region = SmartAccessAiGenerator._region(pixel)
        return {
            "x": min(1.0, pixel_region["x"] / width) if width else 0.0,
            "y": min(1.0, pixel_region["y"] / height) if height else 0.0,
            "width": min(1.0, pixel_region["width"] / width) if width else 0.0,
            "height": min(1.0, pixel_region["height"] / height) if height else 0.0,
        }

    @staticmethod
    def _seconds(value: Any) -> float:
        """把秒、毫秒或字符串时间归一化为秒。"""

        if isinstance(value, str):
            stripped = value.strip().lower()
            match = re.match(r"^(\d+(?:\.\d+)?)\s*(ms|milliseconds?)$", stripped)
            if match:
                return float(match.group(1)) / 1000.0
            if stripped.endswith("s"):
                return float(stripped[:-1].strip())
            value = stripped
        seconds = float(value)
        return seconds / 1000.0 if seconds >= 1000 else seconds

    @staticmethod
    def _workflow_reasoning(
        workflow_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        """生成工作流 AI 摘要。"""

        lines = [
            "## Workflow draft",
            f"goal: {prompt.strip()[:120] or '-'}",
            f"anchor_profile: {context.get('anchor_profile') or '-'}",
            "",
            "### Steps",
        ]
        for index, step in enumerate(workflow_data.get("steps", []) or [], 1):
            value = f" = {step.get('value')}" if step.get("value") is not None else ""
            lines.append(
                f"{index}. {step.get('id')} - {step.get('action')} "
                f"-> {step.get('anchor_id')}{value}"
            )
        return "\n".join(lines)

    @staticmethod
    def _instrument_reasoning(
        profile_data: dict[str, Any],
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        """生成设备接入 AI 摘要。"""

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
                precheck = anchor.get("precheck") or {}
                lines.append(
                    f"- {anchor.get('id')} - action_region={bool(anchor.get('action_region'))} "
                    f"- precheck={precheck.get('mode') or 'none'}"
                )
        else:
            lines.append("- none")
        return "\n".join(lines)

    @staticmethod
    def _friendly_validation_error(exc: ValidationError) -> str:
        """把 Pydantic 错误转成用户可读文本。"""

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

    @staticmethod
    def _origin(base_url: str) -> str:
        """提取请求 Origin。"""

        parts = urlsplit(base_url)
        if not parts.scheme or not parts.netloc:
            return ""
        return f"{parts.scheme}://{parts.netloc}"

    @staticmethod
    def _https_context() -> ssl.SSLContext | None:
        """Build a stable HTTPS context that ignores broken system CA bundles."""

        if certifi is None:
            return ssl.create_default_context()
        cafile = certifi.where()
        if not cafile:
            return ssl.create_default_context()
        try:
            return ssl.create_default_context(cafile=cafile)
        except ssl.SSLError:
            return ssl.create_default_context()

    @staticmethod
    def _format_transport_error(reason: Any) -> str:
        """Format network/TLS failures into a readable message."""

        if isinstance(reason, tuple) and reason:
            reason = reason[0]
        text = str(reason).strip()
        if isinstance(reason, ssl.SSLError) or "ASN1" in text or "PEM" in text:
            return (
                "TLS/SSL 证书加载失败: "
                f"{text}。请检查系统证书链、SSL_CERT_FILE/SSL_CERT_DIR，"
                "或使用可用的 CA bundle。"
            )
        return text

    @staticmethod
    def _should_retry_transport_error(reason: Any) -> bool:
        """Return True for transient connection-reset style failures."""

        if isinstance(reason, RemoteDisconnected):
            return True
        if isinstance(reason, ConnectionResetError):
            return True
        if isinstance(reason, OSError) and getattr(reason, "errno", None) == 10054:
            return True
        return False

    @staticmethod
    def _format_timeout_error(timeout_seconds: float) -> str:
        """Format request timeouts with the configured budget."""

        return f"AI request timed out after {timeout_seconds:g}s"

    @staticmethod
    def _format_http_error(code: int, detail: str) -> str:
        """格式化 HTTP 错误。"""

        collapsed = " ".join(detail.split())
        lowered = collapsed.lower()
        if code == 403 and (
            "1010" in lowered or ("cloudflare" in lowered and "signature" in lowered)
        ):
            return (
                "HTTP 403 Cloudflare 1010: endpoint blocked this request signature. "
                "请检查 SMARTACCESS_AI_USER_AGENT 或更换 provider。"
            )
        return f"HTTP {code}: {collapsed[:500]}"
