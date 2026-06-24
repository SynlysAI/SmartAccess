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


def test_from_env_falls_back_to_legacy_single_group_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEXT/VISION 专用变量未配时，应回退到旧 SMARTACCESS_AI_* 单组变量。

    旧 .env 只有一组 SMARTACCESS_AI_* 时，TEXT 和 VISION 都使用它，
    保证现有部署升级后行为不变。
    """

    for key in (
        "SMARTACCESS_AI_TEXT_PROVIDER",
        "SMARTACCESS_AI_TEXT_BASE_URL",
        "SMARTACCESS_AI_TEXT_MODEL",
        "SMARTACCESS_AI_TEXT_API_KEY",
        "SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_VISION_PROVIDER",
        "SMARTACCESS_AI_VISION_BASE_URL",
        "SMARTACCESS_AI_VISION_MODEL",
        "SMARTACCESS_AI_VISION_API_KEY",
        "SMARTACCESS_AI_VISION_TIMEOUT_SECONDS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMARTACCESS_AI_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("SMARTACCESS_AI_MODEL", "legacy-model")
    monkeypatch.setenv("SMARTACCESS_AI_API_KEY", "sk-legacy")
    monkeypatch.setenv("SMARTACCESS_AI_TIMEOUT_SECONDS", "45")

    settings = AppSettings.from_env()

    # TEXT 和 VISION 都回退到旧单组配置
    assert settings.ai_text_provider == "codex"
    assert settings.ai_text_base_url == "https://legacy.example/v1"
    assert settings.ai_text_model == "legacy-model"
    assert settings.ai_text_api_key == "sk-legacy"
    assert settings.ai_text_timeout_seconds == 45.0

    assert settings.ai_vision_provider == "codex"
    assert settings.ai_vision_base_url == "https://legacy.example/v1"
    assert settings.ai_vision_model == "legacy-model"
    assert settings.ai_vision_api_key == "sk-legacy"
    assert settings.ai_vision_timeout_seconds == 45.0


def test_from_env_falls_back_to_deepseek_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既未配 TEXT/VISION 也未配 SMARTACCESS_AI_* 时，回退到 DEEPSEEK_*。

    早期 .env 只配了 DEEPSEEK_* 这一组，仍需保持向后兼容。
    """

    for key in (
        "SMARTACCESS_AI_TEXT_PROVIDER",
        "SMARTACCESS_AI_TEXT_BASE_URL",
        "SMARTACCESS_AI_TEXT_MODEL",
        "SMARTACCESS_AI_TEXT_API_KEY",
        "SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_VISION_PROVIDER",
        "SMARTACCESS_AI_VISION_BASE_URL",
        "SMARTACCESS_AI_VISION_MODEL",
        "SMARTACCESS_AI_VISION_API_KEY",
        "SMARTACCESS_AI_VISION_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_PROVIDER",
        "SMARTACCESS_AI_BASE_URL",
        "SMARTACCESS_AI_MODEL",
        "SMARTACCESS_AI_API_KEY",
        "SMARTACCESS_AI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_TIMEOUT_SECONDS", "20")

    # 屏蔽 .env 文件读取，确保只依赖环境变量
    monkeypatch.setattr(
        AppSettings, "_read_env_file", staticmethod(lambda path=None: {})
    )

    settings = AppSettings.from_env()

    # TEXT 和 VISION 的 api_key/base_url/model/timeout 都从 DEEPSEEK_* 回退
    assert settings.ai_text_api_key == "sk-deepseek"
    assert settings.ai_text_base_url == "https://api.deepseek.com"
    assert settings.ai_text_model == "deepseek-chat"
    assert settings.ai_text_timeout_seconds == 20.0
    # provider 没有 DEEPSEEK_PROVIDER 变量，回退到默认 "template"
    assert settings.ai_text_provider == "template"

    assert settings.ai_vision_api_key == "sk-deepseek"
    assert settings.ai_vision_base_url == "https://api.deepseek.com"
    assert settings.ai_vision_model == "deepseek-chat"
    assert settings.ai_vision_timeout_seconds == 20.0
    assert settings.ai_vision_provider == "template"


def test_build_runtime_facade_routes_text_and_vision_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """build_runtime_facade 应把 text generator 装给 WorkflowService，
    把 vision generator 装给 RuntimeFacade.ai_generator。"""

    # 屏蔽 .env 文件干扰
    monkeypatch.setattr(
        AppSettings, "_read_env_file", staticmethod(lambda path=None: {})
    )

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

    monkeypatch.setenv("SMARTACCESS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTACCESS_AUTOMATION_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_VISION_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_PLATFORM_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_RABBITMQ_ENABLED", "false")

    from smartaccess.bootstrap.runtime import build_runtime_facade

    settings = AppSettings.from_env()
    facade = build_runtime_facade(settings)

    # WorkflowService 内部装的 draft_generator 应该是 text provider
    workflows_service = facade.providers()["workflows"]
    text_gen = workflows_service._draft_generator
    assert text_gen is not None
    assert text_gen._provider == "deepseek"
    assert text_gen._model == "deepseek-v4-pro"

    # facade 的 ai_generator 应该是 vision provider
    vision_gen = facade._ai_generator
    assert vision_gen is not None
    assert vision_gen._provider == "codex"
    assert vision_gen._model == "gpt-5.4"
