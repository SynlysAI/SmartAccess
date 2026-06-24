"""workflow.yaml 的契约模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, FlexibleContractModel, NonEmptyStr

SIMPLIFIED_WORKFLOW_ACTIONS: tuple[str, ...] = (
    "click",
    "type",
    "hotkey",
    "press_enter",
    "ocr",
    "wait",
)
EXECUTABLE_WORKFLOW_ACTIONS: tuple[str, ...] = (
    "click",
    "type",
    "hotkey",
    "press_enter",
)
LEGACY_WORKFLOW_ACTIONS: tuple[str, ...] = (
    "double_click",
    "wait_until",
    "screenshot_check",
)
MATCH_MODES: tuple[str, ...] = (
    "contains",
    "equals",
    "regex",
    "not_empty",
    "none",
)


class WorkflowMetadata(FlexibleContractModel):
    """工作流草稿和模板的稳定元数据。"""

    workflow_id: NonEmptyStr
    anchor_profile: NonEmptyStr | None = None
    instrument_profile: str | None = Field(default=None, exclude=True)
    author: NonEmptyStr
    lifecycle_state: NonEmptyStr
    experiment_type: str | None = None
    template_id: str | None = None
    template_version: str | None = None

    @model_validator(mode="after")
    def _normalize_profile(self) -> "WorkflowMetadata":
        """兼容旧字段 instrument_profile。"""

        if not self.anchor_profile and self.instrument_profile:
            self.anchor_profile = self.instrument_profile
        if not self.instrument_profile and self.anchor_profile:
            self.instrument_profile = self.anchor_profile
        if not self.anchor_profile:
            raise ValueError("anchor_profile is required")
        return self


class WorkflowIncrementRule(FlexibleContractModel):
    """Runtime-only input increment rule for type steps."""

    pattern: str = "{device_id}-{author}-{date}-{counter:03d}"
    start: int = Field(default=1, ge=0)
    width: int = Field(default=3, ge=1)
    sequence_key: NonEmptyStr = "default"
    date_format: NonEmptyStr = "%Y%m%d"
    min_value: int | None = Field(default=None, ge=0)
    max_value: int | None = Field(default=None, ge=0)
    cycle: bool = False

    @model_validator(mode="after")
    def _normalize_increment_range(self) -> "WorkflowIncrementRule":
        """Validate persistent increment counter bounds."""

        lower = self.min_value if self.min_value is not None else self.start
        if self.max_value is not None and self.max_value < lower:
            raise ValueError("increment_rule.max_value must be >= min_value/start")
        if self.cycle and self.max_value is None:
            raise ValueError("increment_rule.max_value is required when cycle is true")
        return self


class WorkflowStep(FlexibleContractModel):
    """工作流中的一个动作步骤或等待步骤。"""

    id: NonEmptyStr
    anchor_id: NonEmptyStr | None = None
    view_id: NonEmptyStr = "main"
    target: str | None = Field(default=None, exclude=True)
    action: Literal["click", "type", "hotkey", "press_enter", "ocr", "wait"]
    value: Any | None = None
    input_mode: Literal["free", "incrementing"] = "free"
    increment_rule: WorkflowIncrementRule | None = None
    condition: dict[str, Any] | None = Field(default=None, exclude=True)
    expected_text: str | list[str] | None = None
    expected_candidates: list[str] = Field(default_factory=list)
    match_mode: Literal["contains", "equals", "regex", "not_empty", "none"] = "none"
    ignore_case: bool = False
    normalize_text: bool = False
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    timeout_seconds: float | None = Field(default=None, ge=0)
    wait_seconds: float | None = Field(default=None, ge=0)
    requires_confirmation: bool = False
    migration_error: str | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_nullable_lists(cls, raw: Any) -> Any:
        """Normalize nullable UI/YAML fields before strict field validation."""

        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if data.get("expected_candidates") is None:
            data.pop("expected_candidates", None)
        if data.get("match_mode") == "exact":
            data["match_mode"] = "equals"
        condition = data.get("condition")
        if isinstance(condition, dict):
            normalized_condition = dict(condition)
            if normalized_condition.get("match_mode") == "exact":
                normalized_condition["match_mode"] = "equals"
            if normalized_condition.get("operator") == "exact":
                normalized_condition["operator"] = "equals"
            data["condition"] = normalized_condition
        return data

    @model_validator(mode="after")
    def _normalize_expectation(self) -> "WorkflowStep":
        """标准化锚点、等待时间和 OCR 条件。"""

        if not self.anchor_id and self.target:
            self.anchor_id = self.target
        normalized = normalize_condition(self.condition)
        if normalized:
            if self.match_mode == "none" and normalized.get("match_mode"):
                self.match_mode = normalized["match_mode"]
            if self.expected_text is None and normalized.get("expected_text") is not None:
                self.expected_text = normalized["expected_text"]
            if normalized.get("expected_candidates"):
                self.expected_candidates = [
                    str(value) for value in normalized["expected_candidates"]
                ]
            if normalized.get("ignore_case") is not None:
                self.ignore_case = bool(normalized["ignore_case"])
            if normalized.get("normalize_text") is not None:
                self.normalize_text = bool(normalized["normalize_text"])
            if normalized.get("min_confidence") is not None:
                self.min_confidence = float(normalized["min_confidence"])
            if (
                self.timeout_seconds is None
                and normalized.get("timeout_seconds") is not None
            ):
                self.timeout_seconds = float(normalized["timeout_seconds"])
        if self.action == "wait":
            self.input_mode = "free"
            self.increment_rule = None
            self._normalize_wait_step()
            return self
        if self.action != "type":
            self.input_mode = "free"
            self.increment_rule = None
        elif self.input_mode == "incrementing" and self.increment_rule is None:
            self.increment_rule = WorkflowIncrementRule()
        if self.expected_candidates:
            if self.expected_text is None:
                self.expected_text = list(self.expected_candidates)
            elif isinstance(self.expected_text, str):
                values = [self.expected_text, *self.expected_candidates]
                self.expected_text = list(dict.fromkeys(values))
        if self.match_mode == "none":
            self.expected_text = None
            self.expected_candidates = []
            self.timeout_seconds = None
            self.min_confidence = None
        if not self.anchor_id:
            self.migration_error = "anchor_id is required for executable workflow steps"
        return self

    def _normalize_wait_step(self) -> None:
        """标准化等待步骤字段。"""

        if self.wait_seconds is None and self.value is not None:
            self.wait_seconds = _coerce_seconds(self.value)
        if self.wait_seconds is None:
            self.wait_seconds = 1.0
        if self.match_mode == "none":
            self.anchor_id = None
            self.target = None
            self.view_id = "main"
            self.expected_text = None
            self.expected_candidates = []
            self.timeout_seconds = None
            self.min_confidence = None
            return
        if self.expected_candidates:
            if self.expected_text is None:
                self.expected_text = list(self.expected_candidates)
            elif isinstance(self.expected_text, str):
                values = [self.expected_text, *self.expected_candidates]
                self.expected_text = list(dict.fromkeys(values))
        if not self.anchor_id:
            self.migration_error = "anchor_id is required for OCR wait steps"


class WorkflowMigrationError(FlexibleContractModel):
    """无法安全迁移的旧工作流步骤。"""

    id: NonEmptyStr
    action: str
    target: str | None = None
    anchor_id: str | None = None
    reason: NonEmptyStr
    original: dict[str, Any] = Field(default_factory=dict)


class WorkflowOutput(FlexibleContractModel):
    """旧版输出声明的兼容结构。"""

    key: NonEmptyStr
    source: NonEmptyStr


class WorkflowRetryPolicy(FlexibleContractModel):
    """工作流重试策略。"""

    max_attempts: int = Field(default=1, ge=0)


class WorkflowContract(ContractModel):
    """工作流顶层契约。"""

    metadata: WorkflowMetadata
    steps: list[WorkflowStep] = Field(default_factory=list)
    roi_bindings: dict[str, str] = Field(default_factory=dict)
    outputs: list[WorkflowOutput] = Field(default_factory=list)
    retry_policy: WorkflowRetryPolicy = Field(default_factory=WorkflowRetryPolicy)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    migration_errors: list[WorkflowMigrationError] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_steps(cls, raw: Any) -> Any:
        """迁移旧工作流步骤结构。"""

        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        steps, migration_errors = normalize_workflow_steps(data.get("steps") or [])
        data["steps"] = steps
        existing_errors = data.get("migration_errors") or []
        data["migration_errors"] = [*existing_errors, *migration_errors]
        return data

    @model_validator(mode="after")
    def _unique_step_ids(self) -> "WorkflowContract":
        """检查步骤 ID 不重复。"""

        step_ids = [step.id for step in self.steps]
        duplicates = sorted(
            {step_id for step_id in step_ids if step_ids.count(step_id) > 1}
        )
        if duplicates:
            raise ValueError(f"duplicate step ids: {', '.join(duplicates)}")
        return self


def normalize_condition(condition: dict[str, Any] | None) -> dict[str, Any] | None:
    """把旧版 condition 转成 OCR 期望字段。

    Args:
        condition: 旧版条件对象。

    Returns:
        标准化后的条件对象；无条件时返回 None。
    """

    if not condition:
        return None
    operator = condition.get("match_mode") or condition.get("operator") or "contains"
    if operator == "exists":
        operator = "not_empty"
    if operator == "exact":
        operator = "equals"
    if operator not in MATCH_MODES:
        operator = "contains"
    expected = condition.get("expected_text")
    if expected is None:
        expected = condition.get("expected")
    candidates = condition.get("expected_candidates")
    if candidates is None:
        candidates = condition.get("candidates")
    timeout = condition.get("timeout_seconds", condition.get("timeout"))
    normalized: dict[str, Any] = {"match_mode": operator}
    if expected is not None and operator != "not_empty":
        normalized["expected_text"] = expected
    if candidates is not None and operator != "not_empty":
        if isinstance(candidates, (list, tuple)):
            normalized["expected_candidates"] = [
                str(value) for value in candidates if value is not None
            ]
        elif candidates:
            normalized["expected_candidates"] = [str(candidates)]
    for key in ("ignore_case", "normalize_text"):
        if condition.get(key) is not None:
            normalized[key] = bool(condition[key])
    if condition.get("min_confidence") is not None:
        normalized["min_confidence"] = float(condition["min_confidence"])
    if timeout is not None:
        normalized["timeout_seconds"] = _coerce_seconds(timeout)
    return normalized


def normalize_workflow_steps(
    raw_steps: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回标准步骤和迁移错误列表。

    Args:
        raw_steps: 原始步骤列表。

    Returns:
        标准步骤列表和迁移错误列表。
    """

    steps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json", exclude_none=True)
        if not isinstance(raw, dict):
            errors.append(
                {
                    "id": f"legacy_step_{index + 1}",
                    "action": "unknown",
                    "reason": "legacy step is not an object",
                    "original": {"value": raw},
                }
            )
            continue
        step = dict(raw)
        action = str(step.get("action") or "").strip()
        step_id = str(step.get("id") or f"step_{index + 1}")
        if "anchor_id" not in step and step.get("target"):
            step["anchor_id"] = step.get("target")
        if action == "double_click":
            _append_double_click_steps(steps, step, step_id)
            continue
        if action in {"wait_until", "screenshot_check"}:
            _merge_legacy_condition(steps, errors, step)
            continue
        if action == "wait":
            steps.append(_wait_step(step, step_id))
            continue
        if action not in EXECUTABLE_WORKFLOW_ACTIONS:
            errors.append(
                _migration_error(
                    step,
                    f"legacy action '{action or 'unknown'}' must be rebound",
                )
            )
            continue
        clean = _action_step(step, action=action, step_id=step_id)
        flat_condition = _condition_from_flat_step(step)
        if flat_condition:
            _merge_condition_into_step(clean, flat_condition)
        steps.append(clean)
    return steps, errors


def _append_double_click_steps(
    steps: list[dict[str, Any]],
    step: dict[str, Any],
    step_id: str,
) -> None:
    """把双击步骤拆成两次 click。"""

    first = _action_step(step, action="click", step_id=f"{step_id}_click_1")
    second = _action_step(step, action="click", step_id=f"{step_id}_click_2")
    first.pop("expected_text", None)
    first.pop("timeout_seconds", None)
    first["match_mode"] = "none"
    steps.extend([first, second])


def _merge_legacy_condition(
    steps: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    step: dict[str, Any],
) -> None:
    """把旧版 OCR 等待条件合并到前一个动作步骤。"""

    condition = normalize_condition(step.get("condition"))
    if condition is None:
        condition = _condition_from_flat_step(step)
    if steps and condition:
        _merge_condition_into_step(steps[-1], condition)
    else:
        errors.append(
            _migration_error(
                step,
                "legacy OCR wait/check must follow an executable action step and rebind",
            )
        )


def _action_step(raw: dict[str, Any], *, action: str, step_id: str) -> dict[str, Any]:
    """返回清理后的动作步骤。"""

    clean = dict(raw)
    clean["id"] = step_id
    clean["action"] = action
    if "anchor_id" not in clean and clean.get("target"):
        clean["anchor_id"] = clean.get("target")
    clean.pop("target", None)
    clean.pop("condition", None)
    clean.pop("migration_error", None)
    return clean


def _wait_step(raw: dict[str, Any], step_id: str) -> dict[str, Any]:
    """返回清理后的固定等待步骤。"""

    clean = dict(raw)
    clean["id"] = step_id
    clean["action"] = "wait"
    clean.pop("target", None)
    condition = _condition_from_flat_step(clean)
    clean.pop("condition", None)
    if clean.get("wait_seconds") is None and clean.get("value") is not None:
        clean["wait_seconds"] = _coerce_seconds(clean["value"])
    if clean.get("wait_seconds") is None:
        clean["wait_seconds"] = 1.0
    if condition:
        _merge_condition_into_step(clean, condition)
    if clean.get("match_mode") in (None, "none"):
        clean.pop("anchor_id", None)
        clean.pop("expected_text", None)
        clean.pop("expected_candidates", None)
        clean.pop("timeout_seconds", None)
        clean.pop("min_confidence", None)
        clean["match_mode"] = "none"
    return clean


def _condition_from_flat_step(step: dict[str, Any]) -> dict[str, Any] | None:
    """从扁平字段提取 OCR 条件。"""

    match_mode = step.get("match_mode")
    expected_text = step.get("expected_text")
    expected_candidates = step.get("expected_candidates")
    timeout = step.get("timeout_seconds")
    if match_mode in MATCH_MODES and (
        match_mode != "none"
        or expected_text is not None
        or expected_candidates is not None
    ):
        condition: dict[str, Any] = {"match_mode": match_mode}
        if expected_text is not None:
            condition["expected_text"] = expected_text
        if expected_candidates is not None:
            condition["expected_candidates"] = expected_candidates
        if timeout is not None:
            condition["timeout_seconds"] = timeout
        for key in ("ignore_case", "normalize_text", "min_confidence"):
            if step.get(key) is not None:
                condition[key] = step[key]
        return condition
    return normalize_condition(step.get("condition"))


def _merge_condition_into_step(
    step: dict[str, Any],
    condition: dict[str, Any],
) -> None:
    """把 OCR 条件写入动作步骤。"""

    match_mode = condition.get("match_mode")
    if match_mode:
        step["match_mode"] = match_mode
    if condition.get("expected_text") is not None:
        step["expected_text"] = condition["expected_text"]
    if condition.get("expected_candidates") is not None:
        step["expected_candidates"] = condition["expected_candidates"]
    if condition.get("timeout_seconds") is not None:
        step["timeout_seconds"] = condition["timeout_seconds"]
    for key in ("ignore_case", "normalize_text", "min_confidence"):
        if condition.get(key) is not None:
            step[key] = condition[key]


def _migration_error(step: dict[str, Any], reason: str) -> dict[str, Any]:
    """构造标准迁移错误对象。"""

    return {
        "id": str(step.get("id") or "legacy_step"),
        "action": str(step.get("action") or "unknown"),
        "target": step.get("target"),
        "anchor_id": step.get("anchor_id"),
        "reason": reason,
        "original": dict(step),
    }


def _coerce_seconds(value: Any) -> float:
    """把数字或字符串时长转成秒。

    Args:
        value: 数字、毫秒字符串或秒字符串。

    Returns:
        秒数。
    """

    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped.endswith("ms"):
            return float(stripped[:-2].strip()) / 1000.0
        if stripped.endswith("s"):
            return float(stripped[:-1].strip())
        value = stripped
    seconds = float(value)
    if seconds >= 1000:
        return seconds / 1000.0
    return seconds
