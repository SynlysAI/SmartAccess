"""YAML and JSONL helpers for SmartAccess contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

import yaml
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_yaml_contract(path: str | Path, model_type: type[ModelT]) -> ModelT:
    """Load a YAML contract file into a concrete Pydantic model."""

    resolved_path = Path(path)
    raw_data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    return model_type.model_validate(raw_data or {})


def dump_yaml_contract(model: BaseModel, path: str | Path) -> Path:
    """Persist a Pydantic model to UTF-8 YAML using JSON-compatible values."""

    resolved_path = Path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json", exclude_none=True)
    resolved_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_path


def load_jsonl_contracts(path: str | Path, model_type: type[ModelT]) -> list[ModelT]:
    """Load a JSONL stream into a list of Pydantic models."""

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
    """Persist a list of models to JSONL."""

    resolved_path = Path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.model_dump_json(exclude_none=True))
            handle.write("\n")
    return resolved_path
