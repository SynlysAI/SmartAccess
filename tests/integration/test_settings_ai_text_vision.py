"""AppSettings 新增 ai_text_* / ai_vision_* 字段的单元测试。"""

from __future__ import annotations

import pytest

from smartaccess.shared.config.settings import AppSettings


def test_settings_default_ai_text_fields() -> None:
    """未传任何 AI 配置时，ai_text_* 字段取默认值。"""

    settings = AppSettings()
    assert settings.ai_text_provider == "template"
    assert settings.ai_text_base_url == "https://fufei.mossx.ai/v1"
    assert settings.ai_text_model == "GPT-5.4"
    assert settings.ai_text_api_key is None
    assert settings.ai_text_timeout_seconds == 30.0


def test_settings_default_ai_vision_fields() -> None:
    """未传任何 AI 配置时，ai_vision_* 字段取默认值。"""

    settings = AppSettings()
    assert settings.ai_vision_provider == "template"
    assert settings.ai_vision_base_url == "https://fufei.mossx.ai/v1"
    assert settings.ai_vision_model == "GPT-5.4"
    assert settings.ai_vision_api_key is None
    assert settings.ai_vision_timeout_seconds == 30.0


def test_from_env_reads_text_and_vision_specific_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """from_env 应分别读取 SMARTACCESS_AI_TEXT_* 和 _VISION_* 专用变量。"""

    for key in (
        "SMARTACCESS_AI_PROVIDER",
        "SMARTACCESS_AI_BASE_URL",
        "SMARTACCESS_AI_MODEL",
        "SMARTACCESS_AI_API_KEY",
        "SMARTACCESS_AI_TIMEOUT_SECONDS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMARTACCESS_AI_TEXT_PROVIDER", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_API_KEY", "sk-text-key")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS", "60")

    monkeypatch.setenv("SMARTACCESS_AI_VISION_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_BASE_URL", "https://code.ppchat.vip/v1")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_MODEL", "gpt-5.4")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_API_KEY", "sk-vision-key")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_TIMEOUT_SECONDS", "90")

    settings = AppSettings.from_env()

    assert settings.ai_text_provider == "deepseek"
    assert settings.ai_text_base_url == "https://api.deepseek.com/v1"
    assert settings.ai_text_model == "deepseek-v4-pro"
    assert settings.ai_text_api_key == "sk-text-key"
    assert settings.ai_text_timeout_seconds == 60.0

    assert settings.ai_vision_provider == "codex"
    assert settings.ai_vision_base_url == "https://code.ppchat.vip/v1"
    assert settings.ai_vision_model == "gpt-5.4"
    assert settings.ai_vision_api_key == "sk-vision-key"
    assert settings.ai_vision_timeout_seconds == 90.0
