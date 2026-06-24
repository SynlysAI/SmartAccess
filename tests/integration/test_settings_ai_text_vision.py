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
