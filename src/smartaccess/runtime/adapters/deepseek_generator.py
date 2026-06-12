"""DeepSeek-compatible workflow draft generator."""

from __future__ import annotations

from smartaccess.runtime.adapters.openai_compatible_generator import (
    OpenAICompatibleWorkflowGenerator,
)
from smartaccess.shared.config.settings import AIProfileConfig


class DeepSeekWorkflowGenerator(OpenAICompatibleWorkflowGenerator):
    """Generate workflow drafts with DeepSeek's OpenAI-compatible chat API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_seconds: float = 30.0,
        user_agent: str | None = None,
        profiles: dict[str, AIProfileConfig] | None = None,
        active_profile: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="DeepSeek",
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            profiles=profiles,
            active_profile=active_profile,
            wire_api="chat_completions",
        )
