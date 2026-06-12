"""Application-level settings shared across SmartAccess processes."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_AI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def normalize_ai_wire_api(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "chat": "chat_completions",
        "chat_completion": "chat_completions",
        "chat_completions": "chat_completions",
        "responses": "responses",
        "response": "responses",
    }
    return aliases.get(normalized, "chat_completions")


class AIProfileConfig(BaseModel):
    """A selectable OpenAI-compatible model profile."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    profile_id: str
    label: str
    provider: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)
    wire_api: str = Field(default="")

    @model_validator(mode="after")
    def _set_default_wire_api(self) -> "AIProfileConfig":
        self.wire_api = normalize_ai_wire_api(
            self.wire_api or ("responses" if self.provider.lower() == "codex" else "chat_completions")
        )
        return self

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def public_dict(self) -> dict[str, str | bool]:
        return {
            "profile_id": self.profile_id,
            "label": self.label,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "wire_api": self.wire_api,
            "configured": self.configured,
        }


class AppSettings(BaseModel):
    """Runtime settings used by SmartAccess processes and provider wiring."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    workspace_dir: Path = Field(default=Path("workspace"))
    edge_api_host: str = Field(default="127.0.0.1")
    edge_api_port: int = Field(default=7000, ge=1, le=65535)
    internal_api_host: str = Field(default="127.0.0.1")
    internal_api_port: int = Field(default=7100, ge=1, le=65535)
    log_level: str = Field(default="INFO")
    enable_real_providers: bool = Field(default=False)
    automation_provider: str = Field(default="stub")
    vision_provider: str = Field(default="stub")
    platform_provider: str = Field(default="stub")
    ai_user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)
    ai_active_profile: str = Field(default="")
    ai_profiles: dict[str, AIProfileConfig] = Field(default_factory=dict)
    udp_host: str = Field(default="127.0.0.1")
    udp_port: int = Field(default=8889, ge=1, le=65535)
    speclabos_base_url: str | None = Field(default=None)
    speclabos_api_key: str | None = Field(default=None)
    speclabos_timeout_seconds: float = Field(default=20.0, gt=0)

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Build settings from environment variables without pydantic-settings."""

        env_file_values = cls._read_env_file()

        def _get(name: str, default: str | None = None) -> str | None:
            value = os.getenv(name)
            if value in (None, ""):
                value = env_file_values.get(name)
            return value if value not in (None, "") else default

        ai_profiles = cls._build_ai_profiles(_get)
        active_profile = cls._select_active_ai_profile(_get, ai_profiles)

        return cls(
            workspace_dir=Path(_get("SMARTACCESS_WORKSPACE_DIR", "workspace") or "workspace"),
            edge_api_host=_get("SMARTACCESS_EDGE_API_HOST", "127.0.0.1") or "127.0.0.1",
            edge_api_port=int(_get("SMARTACCESS_EDGE_API_PORT", "7000") or "7000"),
            internal_api_host=_get("SMARTACCESS_INTERNAL_API_HOST", "127.0.0.1") or "127.0.0.1",
            internal_api_port=int(_get("SMARTACCESS_INTERNAL_API_PORT", "7100") or "7100"),
            log_level=_get("SMARTACCESS_LOG_LEVEL", "INFO") or "INFO",
            enable_real_providers=(_get("SMARTACCESS_ENABLE_REAL_PROVIDERS", "false") or "false").lower() in {"1", "true", "yes", "on"},
            automation_provider=_get("SMARTACCESS_AUTOMATION_PROVIDER", "stub") or "stub",
            vision_provider=_get("SMARTACCESS_VISION_PROVIDER", "stub") or "stub",
            platform_provider=_get("SMARTACCESS_PLATFORM_PROVIDER", "stub") or "stub",
            ai_user_agent=_get("SMARTACCESS_AI_USER_AGENT", DEFAULT_AI_USER_AGENT) or DEFAULT_AI_USER_AGENT,
            ai_active_profile=active_profile,
            ai_profiles=ai_profiles,
            udp_host=_get("SMARTACCESS_UDP_HOST", "127.0.0.1") or "127.0.0.1",
            udp_port=int(_get("SMARTACCESS_UDP_PORT", "8889") or "8889"),
            speclabos_base_url=_get("SPECLABOS_BASE_URL"),
            speclabos_api_key=_get("SPECLABOS_API_KEY"),
            speclabos_timeout_seconds=float(_get("SPECLABOS_TIMEOUT_SECONDS", "20") or "20"),
        )

    @classmethod
    def _build_ai_profiles(cls, get_value) -> dict[str, AIProfileConfig]:
        requested = [
            item.strip().lower()
            for item in (get_value("SMARTACCESS_AI_PROFILES", "") or "").split(",")
            if item.strip()
        ]
        profiles: dict[str, AIProfileConfig] = {}
        for profile_id in requested:
            profile = cls._profile_from_env(profile_id, get_value)
            profiles[profile.profile_id] = profile
        return profiles

    @classmethod
    def _profile_from_env(cls, profile_id: str, get_value) -> AIProfileConfig:
        suffix = cls._profile_env_suffix(profile_id)
        default_provider = "deepseek" if profile_id == "deepseek" else profile_id
        if default_provider not in {"codex", "openai", "deepseek"}:
            default_provider = "openai-compatible"
        default_base_url = "https://api.deepseek.com" if default_provider == "deepseek" else "https://fufei.mossx.ai/v1"
        default_model = "deepseek-chat" if default_provider == "deepseek" else "GPT-5.4"
        default_wire_api = "responses" if default_provider == "codex" else "chat_completions"
        return AIProfileConfig(
            profile_id=profile_id,
            label=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_LABEL", cls._default_profile_label(profile_id, default_provider)) or cls._default_profile_label(profile_id, default_provider),
            provider=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_PROVIDER", default_provider) or default_provider,
            base_url=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_BASE_URL", default_base_url) or default_base_url,
            model=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_MODEL", default_model) or default_model,
            api_key=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_API_KEY"),
            timeout_seconds=float(get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_TIMEOUT_SECONDS", "30") or "30"),
            user_agent=get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_USER_AGENT", get_value("SMARTACCESS_AI_USER_AGENT", DEFAULT_AI_USER_AGENT)) or DEFAULT_AI_USER_AGENT,
            wire_api=normalize_ai_wire_api(
                get_value(f"SMARTACCESS_AI_PROFILE_{suffix}_WIRE_API", default_wire_api)
                or default_wire_api
            ),
        )

    @staticmethod
    def _profile_env_suffix(profile_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", profile_id).strip("_").upper()

    @staticmethod
    def _default_profile_label(profile_id: str, provider: str) -> str:
        labels = {"codex": "Codex", "deepseek": "DeepSeek", "openai": "OpenAI"}
        return labels.get(provider.lower(), profile_id)

    @staticmethod
    def _select_active_ai_profile(get_value, profiles: dict[str, AIProfileConfig]) -> str:
        requested = (
            get_value("SMARTACCESS_AI_ACTIVE_PROFILE")
            or ""
        ).strip().lower()
        if requested in profiles:
            return requested
        for profile in profiles.values():
            if profile.configured:
                return profile.profile_id
        return next(iter(profiles), "")

    @staticmethod
    def _read_env_file(path: Path | None = None) -> dict[str, str]:
        env_path = path or Path.cwd() / ".env"
        if not env_path.exists():
            return {}
        values: dict[str, str] = {}
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            values[key] = AppSettings._clean_env_value(value)
        return values

    @staticmethod
    def _clean_env_value(value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            return cleaned[1:-1]
        return cleaned

    @property
    def ai_configured(self) -> bool:
        profile = self.ai_active_profile_config
        return bool(profile and profile.configured)

    @property
    def ai_active_profile_config(self) -> AIProfileConfig | None:
        if self.ai_active_profile and self.ai_active_profile in self.ai_profiles:
            return self.ai_profiles[self.ai_active_profile]
        return None

    def ai_profile_public_options(self) -> list[dict[str, str | bool]]:
        return [profile.public_dict() for profile in self.ai_profiles.values()]

    @property
    def speclabos_configured(self) -> bool:
        return bool(self.speclabos_base_url)
