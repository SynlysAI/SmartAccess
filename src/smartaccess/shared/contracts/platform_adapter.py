"""Pydantic models for `platform_adapter.yaml`."""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class AuthConfig(FlexibleContractModel):
    """Platform authentication settings without inline secrets."""

    mode: NonEmptyStr
    secret_ref: NonEmptyStr


class EndpointMap(FlexibleContractModel):
    """SpecLabOS endpoint mappings used by the runtime adapter."""

    health: NonEmptyStr
    fetch_task: NonEmptyStr
    fetch_template: NonEmptyStr
    publish_template: NonEmptyStr
    upload_status: NonEmptyStr
    upload_logs: NonEmptyStr
    upload_results: NonEmptyStr


class AdapterRetryPolicy(FlexibleContractModel):
    """Retry and offline caching policy for platform sync."""

    max_attempts: int = Field(ge=0)
    backoff_seconds: float | None = Field(default=None, ge=0)
    cache_when_offline: bool | None = None


class PlatformAdapterContract(ContractModel):
    """Top-level contract for SmartAccess platform connectivity."""

    base_url: AnyHttpUrl
    auth: AuthConfig
    endpoint_map: EndpointMap
    field_map: dict[str, str] = Field(default_factory=dict)
    retry_policy: AdapterRetryPolicy
