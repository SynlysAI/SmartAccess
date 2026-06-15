from __future__ import annotations

from pathlib import Path

import pytest

from smartaccess.runtime.adapters.ai_stub import TemplatePromptWorkflowGenerator
from smartaccess.runtime.adapters.automation_stub import StubAutomationProvider
from smartaccess.runtime.adapters.deepseek_instrument_generator import DeepSeekInstrumentProfileGenerator
from smartaccess.runtime.adapters.deepseek_generator import DeepSeekWorkflowGenerator
from smartaccess.runtime.adapters.openai_compatible_generator import (
    DEFAULT_AI_USER_AGENT,
    OpenAICompatibleInstrumentProfileGenerator,
    OpenAICompatibleWorkflowGenerator,
)
from smartaccess.runtime.adapters.platform_stub import StubPlatformClient
from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.application.calibration_service import CalibrationService
from smartaccess.runtime.application.evaluation_service import EvaluationService
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.template_service import TemplateService
from smartaccess.runtime.application.workflow_service import WorkflowService
from smartaccess.runtime.application.workspace_settings import (
    AI_PROFILE_DEVICE_ONBOARDING,
    AI_PROFILE_WORKFLOW,
    WorkspaceSettingsStore,
)
from smartaccess.runtime.domain.incident import IncidentType
from smartaccess.runtime.domain.instrument import InstrumentStatus
from smartaccess.runtime.domain.template import TemplateVersionStatus
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.config.settings import AIProfileConfig, AppSettings
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowOutput
from smartaccess.shared.events import EventBus, RuntimeEventName

REPO_ROOT = Path(__file__).resolve().parents[2]


def _draft(workspace: Path) -> WorkflowService:
    return WorkflowService(
        draft_generator=TemplatePromptWorkflowGenerator(),
        workspace_dir=workspace,
    )


def test_calibration_writes_profile(tmp_path: Path) -> None:
    cal = CalibrationService(automation=StubAutomationProvider(), workspace_dir=tmp_path)
    profile = cal.create_profile(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[{"id": "status_button", "main_action": "click"}],
        safety_limits={"max_voltage": 5.0},
    )
    cal.activate("d1")
    assert (tmp_path / "instruments" / "d1" / "instrument_profile.yaml").exists()
    assert profile.device_id == "d1"
    assert cal.status_of("d1") == InstrumentStatus.ACTIVE


def test_workflow_standardize_and_transition_guard(tmp_path: Path) -> None:
    svc = _draft(tmp_path)
    workflow = svc.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    assert svc.standardize_check(workflow).ok

    svc.transition(workflow, WorkflowLifecycleState.CALIBRATED)
    with pytest.raises(ValueError):
        svc.transition(workflow, WorkflowLifecycleState.PUBLISHED)


def test_workflow_update_persists_bindings_and_outputs(tmp_path: Path) -> None:
    svc = _draft(tmp_path)
    workflow = svc.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    workflow.roi_bindings = {"contact_result": "contact_item"}
    workflow.outputs = [WorkflowOutput(key="selected_contact", source="contact_item")]

    svc.update(workflow)

    reloaded = _draft(tmp_path).get("w1")
    assert reloaded is not None
    assert reloaded.roi_bindings == {"contact_result": "contact_item"}
    assert [(out.key, out.source) for out in reloaded.outputs] == [("selected_contact", "contact_item")]
    assert svc.standardize_check(workflow).ok


def test_deepseek_instrument_generator_normalizes_legacy_anchor_shape() -> None:
    raw = {
        "device_id": "weixin_01",
        "window_signature": {"title_contains": "微信", "capture_width": 1000, "capture_height": 800},
        "anchors": [
            {
                "id": "search_bar",
                "roi": {"x": 10, "y": 20, "width": 120, "height": 30},
                "normalized_roi": {"x": 0.01, "y": 0.025, "width": 0.12, "height": 0.0375},
                "action_bindings": [{"action": "click", "requires_confirmation": False}],
                "vision_mode": "none",
            }
        ],
    }

    normalized = DeepSeekInstrumentProfileGenerator._normalize_anchor_profile(
        raw,
        {"device_id": "weixin_01", "title_contains": "微信"},
    )
    profile = AnchorsContract.model_validate(normalized)

    assert profile.profile_id == "weixin_01"
    assert profile.anchors[0].id == "search_bar"
    assert profile.anchors[0].action_region.pixel.width == 120
    assert profile.anchors[0].supported_actions == ["click"]


def test_deepseek_instrument_generator_friendly_validation_error() -> None:
    try:
        AnchorsContract.model_validate({"profile_id": "bad", "anchors": [{}]})
    except Exception as exc:
        message = DeepSeekInstrumentProfileGenerator._friendly_validation_error(exc)
    else:  # pragma: no cover - defensive
        message = ""

    assert "pydantic.dev" not in message
    assert "input_value" not in message
    assert "缺少字段" in message


def test_ai_profile_settings_build_openai_generators(tmp_path: Path) -> None:
    settings = AppSettings(
        workspace_dir=tmp_path,
        ai_active_profile="codex",
        ai_profiles={
            "codex": AIProfileConfig(
                profile_id="codex",
                label="Codex",
                provider="codex",
                base_url="https://fufei.mossx.ai/v1",
                model="GPT-5.4",
                api_key="new-key",
            ),
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="deepseek-key",
            ),
        },
    )

    facade = build_runtime_facade(settings)

    assert isinstance(facade._workflow._draft_generator, OpenAICompatibleWorkflowGenerator)
    assert not isinstance(facade._workflow._draft_generator, DeepSeekWorkflowGenerator)
    assert isinstance(facade._calibration._draft_generator, OpenAICompatibleInstrumentProfileGenerator)
    assert facade.ai_assistant_status().provider == "Codex"
    assert facade.ai_assistant_status().model == "GPT-5.4"
    assert facade.ai_assistant_status().active_profile == "codex"

    assert facade.ai_profile_for_purpose(AI_PROFILE_WORKFLOW) == "codex"
    assert facade.ai_profile_for_purpose(AI_PROFILE_DEVICE_ONBOARDING) == "codex"
    facade.set_ai_profile_preference(AI_PROFILE_DEVICE_ONBOARDING, "deepseek")
    assert facade.ai_profile_for_purpose(AI_PROFILE_WORKFLOW) == "codex"
    assert facade.ai_profile_for_purpose(AI_PROFILE_DEVICE_ONBOARDING) == "codex"
    facade.set_ai_profile_preference(AI_PROFILE_WORKFLOW, "deepseek")
    assert facade.ai_profile_for_purpose(AI_PROFILE_WORKFLOW) == "deepseek"
    assert facade.ai_profile_for_purpose(AI_PROFILE_DEVICE_ONBOARDING) == "codex"


def test_ai_profile_env_loads_selected_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTACCESS_AI_PROFILES", "codex,deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_ACTIVE_PROFILE", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_API_KEY", "new-key")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_BASE_URL", "https://fufei.mossx.ai/v1")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_MODEL", "GPT-5.4")
    monkeypatch.setenv("SMARTACCESS_AI_USER_AGENT", "SmartAccessTest/1.0")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_PROVIDER", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_API_KEY", "deepseek-key")

    settings = AppSettings.from_env()

    assert settings.ai_active_profile == "codex"
    assert settings.ai_active_profile_config is not None
    assert settings.ai_active_profile_config.api_key == "new-key"
    assert settings.ai_active_profile_config.base_url == "https://fufei.mossx.ai/v1"
    assert settings.ai_active_profile_config.model == "GPT-5.4"
    assert settings.ai_active_profile_config.wire_api == "responses"
    assert settings.ai_user_agent == "SmartAccessTest/1.0"


def test_app_settings_loads_dotenv_without_overriding_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "SMARTACCESS_AI_PROFILES=codex",
                "SMARTACCESS_AI_ACTIVE_PROFILE=codex",
                "SMARTACCESS_AI_PROFILE_CODEX_PROVIDER=codex",
                "SMARTACCESS_AI_PROFILE_CODEX_API_KEY=dotenv-key",
                "SMARTACCESS_AI_PROFILE_CODEX_BASE_URL=https://dotenv.example/v1",
                "SMARTACCESS_AI_PROFILE_CODEX_MODEL=DotEnvModel",
                'SMARTACCESS_AI_USER_AGENT="DotEnvAgent/1.0"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_MODEL", "EnvModel")

    settings = AppSettings.from_env()

    assert settings.ai_active_profile == "codex"
    assert settings.ai_active_profile_config is not None
    assert settings.ai_active_profile_config.api_key == "dotenv-key"
    assert settings.ai_active_profile_config.base_url == "https://dotenv.example/v1"
    assert settings.ai_active_profile_config.model == "EnvModel"
    assert settings.ai_active_profile_config.wire_api == "responses"
    assert settings.ai_user_agent == "DotEnvAgent/1.0"


def test_app_settings_loads_multiple_ai_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTACCESS_AI_PROFILES", "codex,deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_ACTIVE_PROFILE", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_BASE_URL", "https://fufei.mossx.ai/v1")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_MODEL", "GPT-5.4")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_CODEX_API_KEY", "codex-key")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_PROVIDER", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("SMARTACCESS_AI_PROFILE_DEEPSEEK_API_KEY", "deepseek-key")

    settings = AppSettings.from_env()

    assert settings.ai_active_profile == "deepseek"
    assert settings.ai_active_profile_config is not None
    assert settings.ai_active_profile_config.api_key == "deepseek-key"
    assert settings.ai_active_profile_config.wire_api == "chat_completions"
    assert set(settings.ai_profiles) == {"codex", "deepseek"}
    assert settings.ai_profiles["codex"].api_key == "codex-key"


def test_workspace_settings_persist_ai_profile_preferences(tmp_path: Path) -> None:
    store = WorkspaceSettingsStore(workspace_dir=tmp_path)

    assert store.ai_profile_preferences() == {
        AI_PROFILE_WORKFLOW: "",
        AI_PROFILE_DEVICE_ONBOARDING: "",
    }

    store.set_ai_profile_preference(AI_PROFILE_WORKFLOW, "codex")
    store.set_ai_profile_preference(AI_PROFILE_DEVICE_ONBOARDING, "deepseek")

    reloaded = WorkspaceSettingsStore(workspace_dir=tmp_path)
    assert reloaded.ai_profile_preferences() == {
        AI_PROFILE_WORKFLOW: "codex",
        AI_PROFILE_DEVICE_ONBOARDING: "deepseek",
    }
    assert "codex-key" not in reloaded.path.read_text(encoding="utf-8")


def test_workspace_settings_ignores_invalid_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "config" / "app_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not-json", encoding="utf-8")

    store = WorkspaceSettingsStore(workspace_dir=tmp_path)

    assert store.ai_profile_preferences() == {
        AI_PROFILE_WORKFLOW: "",
        AI_PROFILE_DEVICE_ONBOARDING: "",
    }


def test_openai_compatible_headers_use_browser_user_agent() -> None:
    generator = OpenAICompatibleWorkflowGenerator(
        api_key="secret",
        base_url="https://fufei.mossx.ai/v1",
        model="GPT-5.4",
        provider_name="Codex",
    )

    headers = generator._headers("https://fufei.mossx.ai/v1")

    assert headers["Authorization"] == "Bearer secret"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == DEFAULT_AI_USER_AGENT
    assert headers["Origin"] == "https://fufei.mossx.ai"
    assert headers["Referer"] == "https://fufei.mossx.ai/"


def test_openai_compatible_request_config_uses_selected_profile_key() -> None:
    generator = OpenAICompatibleWorkflowGenerator(
        api_key="fallback-key",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "codex": AIProfileConfig(
                profile_id="codex",
                label="Codex",
                provider="codex",
                base_url="https://fufei.mossx.ai/v1",
                model="GPT-5.4",
                api_key="codex-key",
            ),
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="deepseek-key",
            ),
        },
        active_profile="codex",
    )

    config = generator._request_config({"ai_profile_id": "deepseek"})
    headers = generator._headers(config["base_url"], api_key=config["api_key"])

    assert config["model"] == "deepseek-chat"
    assert config["base_url"] == "https://api.deepseek.com"
    assert headers["Authorization"] == "Bearer deepseek-key"


def test_codex_profile_uses_responses_api_for_workflow_generation() -> None:
    class CapturingGenerator(OpenAICompatibleWorkflowGenerator):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls: list[tuple[str, dict]] = []

        def _post(self, path, payload, **kwargs):  # noqa: ANN001, ANN002, ANN003
            self.calls.append((path, payload))
            return {
                "output_text": __import__("json").dumps(
                    {
                        "metadata": {
                            "workflow_id": "wf_response",
                            "author": "ai-assistant",
                            "anchor_profile": "d1",
                            "experiment_type": "smoke",
                            "lifecycle_state": "Draft",
                        },
                        "preconditions": [],
                        "steps": [
                            {
                                "id": "step_1",
                                "action": "click",
                                "anchor_id": "start_button",
                                "wait_seconds": 1.0,
                            }
                        ],
                        "retry_policy": {"max_attempts": 2},
                    }
                )
            }

    generator = CapturingGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "codex": AIProfileConfig(
                profile_id="codex",
                label="Codex",
                provider="codex",
                base_url="https://code.ppchat.vip/v1",
                model="gpt-5.4",
                api_key="codex-key",
            )
        },
        active_profile="codex",
    )

    workflow = generator.draft_from_prompt(
        "click start",
        {"workflow_id": "wf_response", "anchor_profile": "d1"},
    )

    assert generator.calls[0][0] == "/responses"
    payload = generator.calls[0][1]
    assert payload["model"] == "gpt-5.4"
    assert "input" in payload
    assert "messages" not in payload
    assert workflow.metadata.workflow_id == "wf_response"


def test_deepseek_profile_keeps_chat_completions_for_workflow_generation() -> None:
    class CapturingGenerator(OpenAICompatibleWorkflowGenerator):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls: list[tuple[str, dict]] = []

        def _post(self, path, payload, **kwargs):  # noqa: ANN001, ANN002, ANN003
            self.calls.append((path, payload))
            return {
                "choices": [
                    {
                        "message": {
                            "content": __import__("json").dumps(
                                {
                                    "metadata": {
                                        "workflow_id": "wf_chat",
                                        "author": "ai-assistant",
                                        "anchor_profile": "d1",
                                        "experiment_type": "smoke",
                                        "lifecycle_state": "Draft",
                                    },
                                    "preconditions": [],
                                    "steps": [
                                        {
                                            "id": "step_1",
                                            "action": "click",
                                            "anchor_id": "start_button",
                                            "wait_seconds": 1.0,
                                        }
                                    ],
                                    "retry_policy": {"max_attempts": 2},
                                }
                            )
                        }
                    }
                ]
            }

    generator = CapturingGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="deepseek-key",
            )
        },
        active_profile="deepseek",
    )

    workflow = generator.draft_from_prompt("click start", {"workflow_id": "wf_chat"})

    assert generator.calls[0][0] == "/chat/completions"
    payload = generator.calls[0][1]
    assert "messages" in payload
    assert "input" not in payload
    assert workflow.metadata.workflow_id == "wf_chat"


def test_explicit_unknown_ai_profile_does_not_fallback_to_active_profile() -> None:
    generator = OpenAICompatibleWorkflowGenerator(
        api_key="fallback-key",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="deepseek-key",
            )
        },
        active_profile="deepseek",
    )

    config = generator._request_config({"ai_profile_id": "codex"})

    assert config["profile_id"] == "codex"
    assert config["label"] == "codex"
    assert config["api_key"] == ""


def test_openai_compatible_cloudflare_1010_error_is_short() -> None:
    generator = OpenAICompatibleWorkflowGenerator(
        api_key="secret",
        base_url="https://fufei.mossx.ai/v1",
        model="GPT-5.4",
        provider_name="Codex",
        user_agent="SmartAccessTest/1.0",
    )
    detail = {
        "title": "Error 1010: Access denied",
        "status": 403,
        "detail": "The site owner has blocked access based on your browser's signature.",
        "err_code": 1010,
        "footer": "x" * 2000,
    }

    message = generator._format_http_error(403, __import__("json").dumps(detail))

    assert "HTTP 403 Cloudflare 1010" in message
    assert "SmartAccessTest/1.0" in message
    assert len(message) < 400
    assert "x" * 100 not in message


def test_deepseek_profile_settings_build_deepseek_generators(tmp_path: Path) -> None:
    settings = AppSettings(
        workspace_dir=tmp_path,
        ai_active_profile="deepseek",
        ai_profiles={
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="legacy-key",
            )
        },
    )

    facade = build_runtime_facade(settings)

    assert isinstance(facade._workflow._draft_generator, DeepSeekWorkflowGenerator)
    assert isinstance(facade._calibration._draft_generator, DeepSeekInstrumentProfileGenerator)


def test_anchor_generator_payload_omits_image_url_by_default() -> None:
    generator = OpenAICompatibleInstrumentProfileGenerator(
        api_key="test",
        base_url="https://example.invalid/v1",
        model="vision-model",
        provider_name="TestProvider",
    )

    with_image = generator._chat_payload(
        "draft anchors",
        {
            "device_id": "d1",
            "capture_width": 100,
            "capture_height": 80,
            "screenshot": {"mime_type": "image/png", "data": "AAAA"},
        },
    )
    without_image = generator._chat_payload("draft anchors", {"device_id": "d1"})

    content = with_image["messages"][1]["content"]
    assert isinstance(content, str)
    assert "image_url" not in content
    assert "screenshot_attached" in content
    assert isinstance(without_image["messages"][1]["content"], str)


def test_codex_profile_uses_responses_api_for_anchor_generation() -> None:
    class CapturingGenerator(OpenAICompatibleInstrumentProfileGenerator):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls: list[tuple[str, dict]] = []

        def _post(self, path, payload, **kwargs):  # noqa: ANN001, ANN002, ANN003
            self.calls.append((path, payload))
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": __import__("json").dumps(
                                    {
                                        "profile_id": "d1",
                                        "window_signature": {
                                            "title_contains": "Demo",
                                            "screenshot_size": {"width": 100, "height": 80},
                                        },
                                        "anchors": [
                                            {
                                                "id": "start_button",
                                                "action_region": {
                                                    "pixel": {
                                                        "x": 10,
                                                        "y": 20,
                                                        "width": 30,
                                                        "height": 12,
                                                    },
                                                    "normalized": {
                                                        "x": 0.1,
                                                        "y": 0.25,
                                                        "width": 0.3,
                                                        "height": 0.15,
                                                    },
                                                },
                                                "supported_actions": ["click"],
                                                "default_wait_seconds": 2.0,
                                                "action_bindings": [
                                                    {
                                                        "action": "click",
                                                        "requires_confirmation": False,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

    generator = CapturingGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "codex": AIProfileConfig(
                profile_id="codex",
                label="Codex",
                provider="codex",
                base_url="https://code.ppchat.vip/v1",
                model="gpt-5.4",
                api_key="codex-key",
            )
        },
        active_profile="codex",
    )

    profile = generator.draft_from_prompt(
        "draft anchors",
        {"device_id": "d1", "capture_width": 100, "capture_height": 80},
    )

    assert generator.calls[0][0] == "/responses"
    payload = generator.calls[0][1]
    assert "input" in payload
    assert "messages" not in payload
    assert profile.profile_id == "d1"
    assert profile.anchors[0].id == "start_button"


def test_anchor_generator_payload_keeps_image_url_for_vision_enabled_profile() -> None:
    generator = OpenAICompatibleInstrumentProfileGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "vision": AIProfileConfig(
                profile_id="vision",
                label="Vision",
                provider="openai-vision",
                base_url="https://vision.example/v1",
                model="vision-model",
                api_key="vision-key",
            )
        },
        active_profile="vision",
    )

    payload = generator._chat_payload(
        "draft anchors",
        {
            "device_id": "d1",
            "capture_width": 100,
            "capture_height": 80,
            "screenshot": {"mime_type": "image/png", "data": "AAAA"},
            "ai_profile_id": "vision",
        },
    )

    content = payload["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_codex_anchor_generator_payload_omits_image_url_content_part() -> None:
    generator = OpenAICompatibleInstrumentProfileGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Fallback",
        profiles={
            "codex": AIProfileConfig(
                profile_id="codex",
                label="Codex",
                provider="codex",
                base_url="https://fufei.mossx.ai/v1",
                model="GPT-5.4",
                api_key="codex-key",
            )
        },
        active_profile="codex",
    )

    payload = generator._chat_payload(
        "draft anchors",
        {
            "device_id": "d1",
            "capture_width": 100,
            "capture_height": 80,
            "screenshot": {"mime_type": "image/png", "data": "AAAA"},
            "ai_profile_id": "codex",
        },
    )

    content = payload["messages"][1]["content"]
    assert isinstance(content, str)
    assert "image_url" not in content
    assert "screenshot_attached" in content


def test_anchor_generation_error_uses_selected_profile_label() -> None:
    class FailingGenerator(OpenAICompatibleInstrumentProfileGenerator):
        def _post(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("boom")

    generator = FailingGenerator(
        api_key="fallback",
        base_url="https://fallback.invalid/v1",
        model="fallback-model",
        provider_name="Codex",
        profiles={
            "deepseek": AIProfileConfig(
                profile_id="deepseek",
                label="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                api_key="deepseek-key",
            )
        },
        active_profile="codex",
    )

    with pytest.raises(RuntimeError, match="DeepSeek anchor generation failed"):
        generator.draft_from_prompt(
            "draft anchors",
            {
                "device_id": "d1",
                "ai_profile_id": "deepseek",
            },
        )


def test_udp_workspace_draft_standardizes(tmp_path: Path) -> None:
    base = REPO_ROOT / "workspace"
    if not (base / "anchors" / "serial_debug_assistant_udp" / "anchors.yaml").exists():
        pytest.skip("local workspace UDP assets are not present")
    profile = load_yaml_contract(
        base / "anchors" / "serial_debug_assistant_udp" / "anchors.yaml",
        AnchorsContract,
    )
    workflow = load_yaml_contract(
        base / "workflows" / "wf_serial_debug_assistant_udp_send" / "draft.yaml",
        WorkflowContract,
    )

    dump_yaml_contract(profile, tmp_path / "anchors" / profile.profile_id / "anchors.yaml")
    svc = WorkflowService(draft_generator=None, workspace_dir=tmp_path)
    check = svc.standardize_check(workflow)

    assert check.ok, check.issues
    assert workflow.metadata.anchor_profile == "serial_debug_assistant_udp"
    assert workflow.steps[-1].expected_text == "SmartAccess UDP validation"


def test_template_publish_supersede_and_rollback(tmp_path: Path) -> None:
    bus = EventBus()
    svc = TemplateService(platform=StubPlatformClient(), workspace_dir=tmp_path, event_bus=bus)
    drafts = _draft(tmp_path)

    v1 = drafts.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    v1.metadata.template_id = "t1"
    v1.metadata.template_version = "1.0.0"
    svc.publish(v1)

    v2 = v1.model_copy(deep=True)
    v2.metadata.template_version = "1.1.0"
    svc.publish(v2)

    versions = {r.identity.template_version: r.status for r in svc.list_versions("t1")}
    assert versions["1.0.0"] == TemplateVersionStatus.SUPERSEDED
    assert versions["1.1.0"] == TemplateVersionStatus.PUBLISHED

    svc.rollback("t1", "1.0.0")
    versions = {r.identity.template_version: r.status for r in svc.list_versions("t1")}
    assert versions["1.0.0"] == TemplateVersionStatus.PUBLISHED
    assert versions["1.1.0"] == TemplateVersionStatus.ROLLED_BACK


def test_platform_outbox_retries_then_fails() -> None:
    bus = EventBus()
    failures: list[RuntimeEventName] = []
    bus.subscribe(lambda e: failures.append(e.name))
    sync = PlatformSyncService(
        platform=StubPlatformClient(offline=True),
        event_bus=bus,
        max_attempts=2,
    )
    sync.enqueue("status", {"run": "s1"})

    assert sync.sync().pending == 1
    stats = sync.sync()
    assert stats.pending == 0
    assert stats.failed == 1
    assert RuntimeEventName.PLATFORM_SYNC_FAILED in failures


def test_incident_manual_confirm_flow() -> None:
    bus = EventBus()
    seen: list[RuntimeEventName] = []
    bus.subscribe(lambda e: seen.append(e.name))
    svc = IncidentService(event_bus=bus)

    incident = svc.open(
        session_id="s1",
        step_id="start_run",
        incident_type=IncidentType.SAFETY_LIMIT_VIOLATION,
        detail="参数越界",
    )
    assert incident.requires_manual_confirm
    assert RuntimeEventName.RUN_BLOCKED in seen

    svc.confirm(incident.incident_id)
    assert incident.resolved
    assert RuntimeEventName.RUN_RECOVERED in seen


def test_evaluation_loads_seven_key_cases() -> None:
    svc = EvaluationService(cases_dir=REPO_ROOT / "ai/harness/evals/cases")
    results = svc.run_all()
    assert len(results) == 7
    assert all(r.passed for r in results)


@pytest.mark.parametrize(
    ("example_dir", "workflow_id", "ocr_step_id", "expected_text"),
    [
        (
            "serial_debug_assistant_udp",
            "wf_serial_debug_assistant_udp_send",
            "send_udp_payload",
            "SmartAccess UDP validation",
        ),
        (
            "windows_calculator",
            "wf_windows_calculator_12_plus_34",
            "verify_result_46",
            "46",
        ),
    ],
)
def test_capability_example_assets_are_standardized(
    tmp_path: Path,
    example_dir: str,
    workflow_id: str,
    ocr_step_id: str,
    expected_text: str,
) -> None:
    base = REPO_ROOT / "docs/contracts/examples" / example_dir
    profile = load_yaml_contract(base / "anchors.yaml", AnchorsContract)
    workflow = load_yaml_contract(base / "workflow.yaml", WorkflowContract)

    assert workflow.metadata.workflow_id == workflow_id
    assert workflow.metadata.anchor_profile == profile.profile_id

    dump_yaml_contract(profile, tmp_path / "anchors" / profile.profile_id / "anchors.yaml")
    svc = WorkflowService(draft_generator=None, workspace_dir=tmp_path)
    check = svc.standardize_check(workflow)
    assert check.ok, check.issues

    ocr_step = next(step for step in workflow.steps if step.id == ocr_step_id)
    anchor = profile.anchor_map()[ocr_step.anchor_id]
    assert ocr_step.expected_text == expected_text
    assert ocr_step.match_mode == "contains"
    assert anchor.observe_region is not None
