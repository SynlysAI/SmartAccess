"""SmartAccess v2 契约基础类型。"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

NonEmptyStr = Annotated[str, Field(min_length=1)]
JsonMap = dict[str, Any]


class ContractModel(BaseModel):
    """顶层契约模型基类。"""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class FlexibleContractModel(BaseModel):
    """允许向前兼容扩展字段的嵌套契约模型基类。"""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
    )
