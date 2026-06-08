"""Base types shared by all SmartAccess contract models."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

NonEmptyStr = Annotated[str, Field(min_length=1)]
JsonMap = dict[str, Any]


class ContractModel(BaseModel):
    """Strict base model for top-level contracts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class FlexibleContractModel(BaseModel):
    """Extensible base model for nested blocks that need forward compatibility."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
    )
