"""解析工作流输入步骤中的运行时占位符。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import uuid4

from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowStep


INPUT_PLACEHOLDER = "{input}"
DATE_PLACEHOLDER = "{date}"


@dataclass(frozen=True, slots=True)
class RuntimeInputField:
    """工作流运行前需要人工填写的输入字段。"""

    step_id: str
    action: str
    anchor_id: str | None
    template: str


def runtime_input_fields(workflow: WorkflowContract) -> list[RuntimeInputField]:
    """返回工作流中所有需要人工填写的输入字段。

    Args:
        workflow: 待执行的工作流。

    Returns:
        按工作流步骤顺序排列的运行前输入字段。
    """

    fields: list[RuntimeInputField] = []
    for step in workflow.steps:
        template = _runtime_input_template(step)
        if template is None:
            continue
        fields.append(
            RuntimeInputField(
                step_id=step.id,
                action=step.action,
                anchor_id=step.anchor_id,
                template=template,
            )
        )
    return fields


def resolve_runtime_input_placeholders(
    workflow: WorkflowContract,
    runtime_values: Mapping[str, str] | None = None,
) -> WorkflowContract:
    """用运行前填写的内容和唯一时间标识解析输入步骤。

    Args:
        workflow: 待执行的工作流。
        runtime_values: 以步骤 ID 为键的人工输入值。

    Returns:
        已替换 `{input}` 和 `{date}` 占位符的运行时工作流副本。

    Raises:
        ValueError: 存在未提供的运行时输入时抛出。
    """

    values = {key: str(value) for key, value in (runtime_values or {}).items()}
    fields = runtime_input_fields(workflow)
    missing_step_ids = [field.step_id for field in fields if field.step_id not in values]
    if missing_step_ids:
        raise ValueError(
            "缺少运行时输入: " + ", ".join(missing_step_ids)
        )

    date_value = _unique_date_value()
    steps = [
        _resolve_step(step, values, date_value)
        for step in workflow.steps
    ]
    return workflow.model_copy(update={"steps": steps})


def _runtime_input_template(step: WorkflowStep) -> str | None:
    """返回步骤中包含 `{input}` 的参数文本。

    Args:
        step: 待检查的工作流步骤。

    Returns:
        需要人工填写时返回参数模板，否则返回 None。
    """

    if step.action == "type" and step.input_mode == "free":
        value = str(step.value or "")
        return value if INPUT_PLACEHOLDER in value else None
    if step.action != "ocr":
        return None
    expected_text = _text_template(step.expected_text)
    if expected_text and INPUT_PLACEHOLDER in expected_text:
        return expected_text
    for candidate in step.expected_candidates:
        if INPUT_PLACEHOLDER in candidate:
            return candidate
    return None


def _resolve_step(
    step: WorkflowStep,
    runtime_values: Mapping[str, str],
    date_value: str,
) -> WorkflowStep:
    """解析单个输入步骤中的占位符。

    Args:
        step: 原始工作流步骤。
        runtime_values: 以步骤 ID 为键的人工输入值。
        date_value: 当前运行的唯一时间标识。

    Returns:
        已解析的步骤；非自由输入步骤保持不变。
    """

    if step.action == "type" and step.input_mode == "free":
        value = str(step.value or "")
        resolved = _replace_placeholders(value, step.id, runtime_values, date_value)
        return step.model_copy(update={"value": resolved})
    if step.action != "ocr":
        return step
    expected_text = _replace_text_value(
        step.expected_text,
        step.id,
        runtime_values,
        date_value,
    )
    expected_candidates = [
        _replace_placeholders(candidate, step.id, runtime_values, date_value)
        for candidate in step.expected_candidates
    ]
    return step.model_copy(
        update={
            "expected_text": expected_text,
            "expected_candidates": expected_candidates,
        }
    )


def _text_template(value: str | list[str] | None) -> str:
    """将 OCR 期望值转换为用于表单提示的文本。"""

    if isinstance(value, list):
        return " | ".join(value)
    return str(value or "")


def _replace_text_value(
    value: str | list[str] | None,
    step_id: str,
    runtime_values: Mapping[str, str],
    date_value: str,
) -> str | list[str] | None:
    """替换 OCR 单值或候选列表中的运行时占位符。"""

    if isinstance(value, list):
        return [
            _replace_placeholders(item, step_id, runtime_values, date_value)
            for item in value
        ]
    if value is None:
        return None
    return _replace_placeholders(value, step_id, runtime_values, date_value)


def _replace_placeholders(
    value: str,
    step_id: str,
    runtime_values: Mapping[str, str],
    date_value: str,
) -> str:
    """替换一个文本值中的 `{input}` 和 `{date}` 占位符。"""

    resolved = value.replace(
        INPUT_PLACEHOLDER,
        runtime_values.get(step_id, INPUT_PLACEHOLDER),
    )
    return resolved.replace(DATE_PLACEHOLDER, date_value)


def _unique_date_value() -> str:
    """生成适用于文件名的唯一时间标识。"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{timestamp}_{uuid4().hex[:8]}"
