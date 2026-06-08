"""Application-level settings shared across SmartAccess processes."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


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
    workflow_generator_provider: str = Field(default="template")
    udp_host: str = Field(default="127.0.0.1")
    udp_port: int = Field(default=8889, ge=1, le=65535)
    deepseek_api_key: str | None = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0)
    speclabos_base_url: str | None = Field(default=None)
    speclabos_api_key: str | None = Field(default=None)
    speclabos_timeout_seconds: float = Field(default=20.0, gt=0)

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Build settings from environment variables without pydantic-settings."""

        def _get(name: str, default: str | None = None) -> str | None:
            value = os.getenv(name)
            return value if value not in (None, "") else default

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
            workflow_generator_provider=_get("SMARTACCESS_WORKFLOW_GENERATOR", "template") or "template",
            udp_host=_get("SMARTACCESS_UDP_HOST", "127.0.0.1") or "127.0.0.1",
            udp_port=int(_get("SMARTACCESS_UDP_PORT", "8889") or "8889"),
            deepseek_api_key=_get("DEEPSEEK_API_KEY"),
            deepseek_base_url=_get("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com",
            deepseek_model=_get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat",
            deepseek_timeout_seconds=float(_get("DEEPSEEK_TIMEOUT_SECONDS", "30") or "30"),
            speclabos_base_url=_get("SPECLABOS_BASE_URL"),
            speclabos_api_key=_get("SPECLABOS_API_KEY"),
            speclabos_timeout_seconds=float(_get("SPECLABOS_TIMEOUT_SECONDS", "20") or "20"),
        )

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def speclabos_configured(self) -> bool:
        return bool(self.speclabos_base_url)
