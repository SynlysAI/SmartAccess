"""SmartAccess v2 契约 YAML 和 JSONL 读写工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, TypeVar

import yaml
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_yaml_contract(path: str | Path, model_type: type[ModelT]) -> ModelT:
    """读取 YAML 契约文件。

    Args:
        path: YAML 文件路径。
        model_type: 目标 Pydantic 模型类型。

    Returns:
        已校验的契约模型。
    """

    resolved_path = Path(path)
    raw_data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    return model_type.model_validate(raw_data or {})


def dump_yaml_contract(model: BaseModel, path: str | Path) -> Path:
    """把契约模型写入 UTF-8 YAML 文件。

    Args:
        model: 要写入的 Pydantic 模型。
        path: 输出文件路径。

    Returns:
        实际写入路径。
    """

    resolved_path = Path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json", exclude_none=True)
    resolved_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_path


def load_jsonl_contracts(path: str | Path, model_type: type[ModelT]) -> list[ModelT]:
    """读取 JSONL 契约流。

    Args:
        path: JSONL 文件路径。
        model_type: 目标 Pydantic 模型类型。

    Returns:
        已校验的模型列表。
    """

    resolved_path = Path(path)
    records: list[ModelT] = []
    with resolved_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            records.append(model_type.model_validate_json(stripped))
    return records


def dump_jsonl_contracts(records: Iterable[BaseModel], path: str | Path) -> Path:
    """把模型序列写入 JSONL 文件。

    Args:
        records: 要写入的模型序列。
        path: 输出文件路径。

    Returns:
        实际写入路径。
    """

    resolved_path = Path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.model_dump_json(exclude_none=True))
            handle.write("\n")
    return resolved_path
