"""Template version domain types (SPEC §4, §5.2).

A published workflow becomes a stable template identified by
``template_id + template_version`` in the SpecLabOS template center.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TemplateVersionStatus(StrEnum):
    """Lifecycle of a template version in the central template store."""

    DRAFT = "Draft"
    STANDARDIZED = "Standardized"
    PUBLISHED = "Published"
    SUPERSEDED = "Superseded"
    ROLLED_BACK = "RolledBack"


@dataclass(frozen=True, slots=True)
class TemplateIdentity:
    """Stable identity of a published template (never a runtime request_id)."""

    template_id: str
    template_version: str

    def __str__(self) -> str:
        return f"{self.template_id}@{self.template_version}"
