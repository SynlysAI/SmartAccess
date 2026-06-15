"""DeepSeek-compatible anchor profile draft generator."""

from __future__ import annotations

from smartaccess.runtime.adapters.openai_compatible_generator import (
    OpenAICompatibleInstrumentProfileGenerator,
)
from smartaccess.shared.config.settings import AIProfileConfig


class DeepSeekInstrumentProfileGenerator(OpenAICompatibleInstrumentProfileGenerator):
    """Generate reviewable anchor profiles with DeepSeek's chat API."""

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
