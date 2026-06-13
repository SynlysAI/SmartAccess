"""模板版本领域类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TemplateVersionStatus(StrEnum):
    """模板版本生命周期状态。"""

    DRAFT = "Draft"
    STANDARDIZED = "Standardized"
    PUBLISHED = "Published"
    SUPERSEDED = "Superseded"
    ROLLED_BACK = "RolledBack"


@dataclass(frozen=True, slots=True)
class TemplateIdentity:
    """模板版本稳定身份。"""

    template_id: str
    template_version: str

    def __str__(self) -> str:
        """返回模板身份字符串。"""

        return f"{self.template_id}@{self.template_version}"
