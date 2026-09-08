"""Platform adapter contract models."""

from __future__ import annotations

from pydantic import AnyUrl, Field

from .base import ContractModel, FlexibleContractModel


class PlatformAuth(FlexibleContractModel):
    """Authentication metadata for a platform adapter."""

    mode: str | None = None
    secret_ref: str | None = None


class PlatformEndpointMap(FlexibleContractModel):
    """Known platform endpoint names used by SmartAccess integrations."""

    health: str | None = None
    fetch_task: str | None = None
    fetch_template: str | None = None
    publish_template: str | None = None
    delete_template: str | None = None
    upload_status: str | None = None
    upload_logs: str | None = None
    upload_trace: str | None = None


class PlatformRetryPolicy(FlexibleContractModel):
    """Retry and offline behavior for platform calls."""

    max_attempts: int = Field(default=1, ge=0)
    backoff_seconds: float = Field(default=0.0, ge=0)
    cache_when_offline: bool = False


class PlatformAdapterContract(ContractModel):
    """Top-level platform adapter contract."""

    base_url: AnyUrl | str | None = None
    auth: PlatformAuth | None = None
    endpoint_map: PlatformEndpointMap = Field(default_factory=PlatformEndpointMap)
    field_map: dict[str, str] = Field(default_factory=dict)
    retry_policy: PlatformRetryPolicy = Field(default_factory=PlatformRetryPolicy)
