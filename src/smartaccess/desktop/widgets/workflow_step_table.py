"""工作流步骤表格组件。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from string import Formatter
import re
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.widgets.condition_editor import ConditionEditor
from smartaccess.desktop.widgets.table_style import (
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    TableCheckBox,
    configure_data_table,
    interactive_header,
    set_embedded_editor_height,
)
from smartaccess.shared.contracts.workflow import (
    DEFAULT_ACTION_WAIT_SECONDS,
    DEFAULT_OCR_POLL_INTERVAL_SECONDS,
    DEFAULT_OCR_TIMEOUT_SECONDS,
)

ACTION_OPTIONS = [
    ("click", "单击"),
    ("type", "输入"),
    ("hotkey", "快捷键"),
    ("press_enter", "回车"),
    ("ocr", "OCR识别"),
    ("wait", "等待"),
]


INPUT_MODE_OPTIONS = [
    ("free", "自由输入"),
    ("incrementing", "递增式"),
]
DEFAULT_INCREMENT_RULE = {
    "pattern": "{device_id}-{author}-{date}-{counter:03d}",
    "start": 1,
    "width": 3,
    "sequence_key": "default",
    "date_format": "%Y%m%d",
    "min_value": None,
    "max_value": None,
    "cycle": False,
}
INCREMENT_PLACEHOLDERS = {
    "device_id",
    "author",
    "date",
    "counter",
    "workflow_id",
    "workflow_name",
    "session",
}
COUNTER_TOKEN_RE = re.compile(r"\{counter(?::0?\d*d)?\}")


def _increment_rule(rule: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a normalized increment rule dictionary."""

    normalized = dict(DEFAULT_INCREMENT_RULE)
    if rule:
        normalized.update(
            {
                key: value
                for key, value in rule.items()
                if key
                in {
                    "pattern",
                    "start",
                    "width",
                    "sequence_key",
                    "date_format",
                    "min_value",
                    "max_value",
                    "cycle",
                }
            }
        )
    if not normalized.get("pattern"):
        normalized["pattern"] = DEFAULT_INCREMENT_RULE["pattern"]
    if normalized.get("start") is None:
        normalized["start"] = DEFAULT_INCREMENT_RULE["start"]
    if normalized.get("width") is None:
        normalized["width"] = DEFAULT_INCREMENT_RULE["width"]
    if not normalized.get("sequence_key"):
        normalized["sequence_key"] = DEFAULT_INCREMENT_RULE["sequence_key"]
    if not normalized.get("date_format"):
        normalized["date_format"] = DEFAULT_INCREMENT_RULE["date_format"]
    normalized["pattern"] = str(normalized["pattern"])
    normalized["start"] = int(normalized["start"])
    normalized["width"] = int(normalized["width"])
    normalized["sequence_key"] = str(normalized["sequence_key"])
    normalized["date_format"] = str(normalized["date_format"])
    normalized["min_value"] = (
        int(normalized["min_value"])
        if normalized.get("min_value") is not None
        else None
    )
    normalized["max_value"] = (
        int(normalized["max_value"])
        if normalized.get("max_value") is not None
        else None
    )
    normalized["cycle"] = bool(normalized.get("cycle"))
    return normalized


def _increment_context(context: dict[str, str] | None = None) -> dict[str, str]:
    """Return preview values used by the increment template editor."""

    values = {
        "device_id": "设备ID",
        "author": "作者",
        "workflow_id": "workflow_id",
        "workflow_name": "workflow_id",
        "session": "session",
        "date": datetime.now().strftime("%Y%m%d"),
    }
    if context:
        values.update({key: str(value) for key, value in context.items() if value})
    return values


def _format_increment_preview(
    rule: dict[str, Any] | None,
    context: dict[str, str] | None = None,
    counter: int | None = None,
) -> tuple[str, str | None]:
    """Format an increment rule preview and return an optional validation error."""

    rule = _increment_rule(rule)
    values = _increment_context(context)
    values["date"] = datetime.now().strftime(str(rule["date_format"]))
    values["counter"] = int(rule["start"] if counter is None else counter)
    try:
        _validate_increment_pattern(rule["pattern"])
        _validate_increment_rule(rule)
        return rule["pattern"].format(**values), None
    except Exception as exc:  # noqa: BLE001 - shown as form validation text.
        return "", str(exc)


def _validate_increment_pattern(pattern: str) -> None:
    """Validate supported increment template fields."""

    fields = []
    for _literal, field_name, format_spec, _conversion in Formatter().parse(pattern):
        if not field_name:
            continue
        name = field_name.split(".", 1)[0].split("[", 1)[0]
        fields.append(name)
        if name not in INCREMENT_PLACEHOLDERS:
            raise ValueError(f"Unsupported placeholder: {{{name}}}")
        if name == "counter" and format_spec and not re.fullmatch(r"0?\d*d", format_spec):
            raise ValueError("Counter format must look like {counter} or {counter:03d}")
    if "counter" not in fields:
        raise ValueError("Pattern must include {counter}")


def _validate_increment_rule(rule: dict[str, Any]) -> None:
    """Validate UI-editable increment rule fields."""

    datetime.now().strftime(str(rule["date_format"]))
    lower = rule["min_value"] if rule["min_value"] is not None else rule["start"]
    if rule["max_value"] is not None and rule["max_value"] < lower:
        raise ValueError("max_value must be >= min_value/start")
    if rule["cycle"] and rule["max_value"] is None:
        raise ValueError("cycle requires max_value")


def _sync_counter_width(pattern: str, width: int) -> str:
    """Apply the configured width to the first counter placeholder."""

    replacement = f"{{counter:0{width}d}}"
    if COUNTER_TOKEN_RE.search(pattern):
        return COUNTER_TOKEN_RE.sub(replacement, pattern, count=1)
    return pattern


class IncrementRuleDialog(QDialog):
    """Dialog for editing a single row's incrementing input template."""

    def __init__(
        self,
        rule: dict[str, Any] | None,
        context: dict[str, str] | None = None,
        preview_counter: Callable[[dict[str, Any]], int | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("配置递增式输入")
        self._context = _increment_context(context)
        self._preview_counter = preview_counter
        self._syncing_width = False
        current = _increment_rule(rule)

        self._sequence_key = QLineEdit(str(current["sequence_key"]))
        self._date_format = QLineEdit(str(current["date_format"]))
        self._pattern = QLineEdit(str(current["pattern"]))
        self._start = QSpinBox()
        self._start.setRange(0, 999999)
        self._start.setValue(int(current["start"]))
        self._width = QSpinBox()
        self._width.setRange(1, 12)
        self._width.setValue(int(current["width"]))
        self._min_value = QSpinBox()
        self._min_value.setRange(-1, 999999)
        self._min_value.setSpecialValueText("未设置")
        self._min_value.setValue(
            int(current["min_value"]) if current["min_value"] is not None else -1
        )
        self._max_value = QSpinBox()
        self._max_value.setRange(-1, 999999)
        self._max_value.setSpecialValueText("未设置")
        self._max_value.setValue(
            int(current["max_value"]) if current["max_value"] is not None else -1
        )
        self._cycle = QCheckBox("达到最大值后循环")
        self._cycle.setChecked(bool(current["cycle"]))
        self._preview = QLineEdit()
        self._preview.setReadOnly(True)
        self._error = QLabel("")
        self._error.setObjectName("FormError")
        self._hint = QLabel(
            "可用占位符：{device_id}、{author}、{date}、{counter}、"
            "{workflow_id}、{workflow_name}、{session}"
        )
        self._hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("变量名", self._sequence_key)
        form.addRow("模板", self._pattern)
        form.addRow("日期格式", self._date_format)
        form.addRow("起始值", self._start)
        form.addRow("计数位数", self._width)
        form.addRow("最小值", self._min_value)
        form.addRow("最大值", self._max_value)
        form.addRow("循环", self._cycle)
        form.addRow("本次预览值", self._preview)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._hint)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        self._pattern.textChanged.connect(lambda _text: self._refresh_preview())
        self._sequence_key.textChanged.connect(lambda _text: self._refresh_preview())
        self._date_format.textChanged.connect(lambda _text: self._refresh_preview())
        self._start.valueChanged.connect(lambda _value: self._refresh_preview())
        self._width.valueChanged.connect(self._width_changed)
        self._min_value.valueChanged.connect(lambda _value: self._refresh_preview())
        self._max_value.valueChanged.connect(lambda _value: self._refresh_preview())
        self._cycle.toggled.connect(lambda _checked: self._refresh_preview())
        self._refresh_preview()

    def rule(self) -> dict[str, Any]:
        """Return the edited increment rule."""

        return {
            "pattern": self._pattern.text().strip(),
            "start": int(self._start.value()),
            "width": int(self._width.value()),
            "sequence_key": self._sequence_key.text().strip() or "default",
            "date_format": self._date_format.text().strip() or "%Y%m%d",
            "min_value": (
                int(self._min_value.value())
                if self._min_value.value() >= 0
                else None
            ),
            "max_value": (
                int(self._max_value.value())
                if self._max_value.value() >= 0
                else None
            ),
            "cycle": bool(self._cycle.isChecked()),
        }

    def _width_changed(self, width: int) -> None:
        if self._syncing_width:
            return
        self._syncing_width = True
        try:
            updated = _sync_counter_width(self._pattern.text(), int(width))
            if updated != self._pattern.text():
                self._pattern.setText(updated)
        finally:
            self._syncing_width = False
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        rule = self.rule()
        counter = self._preview_counter(rule) if self._preview_counter else None
        preview, error = _format_increment_preview(rule, self._context, counter)
        self._preview.setText(preview)
        self._error.setText(error or "")
        button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if button is not None:
            button.setEnabled(error is None and bool(rule["pattern"]))


class InputValueEditor(QWidget):
    """Value cell editor that switches between free and incrementing input."""

    changed = pyqtSignal()

    def __init__(
        self,
        *,
        value: Any | None = None,
        input_mode: str = "free",
        increment_rule: dict[str, Any] | None = None,
        context: dict[str, str] | None = None,
        preview_counter: Callable[[dict[str, Any]], int | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = "free"
        self._rule = _increment_rule(increment_rule) if increment_rule is not None else None
        self._context = _increment_context(context)
        self._preview_counter = preview_counter

        self._free_value = QLineEdit("" if value is None else str(value))
        set_embedded_editor_height(self._free_value)
        self._free_value.textChanged.connect(lambda _text: self.changed.emit())
        self._preview = QLineEdit()
        self._preview.setReadOnly(True)
        self._preview.setToolTip("递增式输入预览，运行时会写入 trace 的 action.value")
        set_embedded_editor_height(self._preview)
        self._config = QPushButton("配置")
        self._config.setObjectName("TableAction")
        self._config.setToolTip("配置本行的递增式输入模板")
        self._config.clicked.connect(self._configure_rule)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._free_value, 1)
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._config)
        self.set_input_mode(input_mode)

    def set_context(
        self,
        context: dict[str, str] | None,
        preview_counter: Callable[[dict[str, Any]], int | None] | None = None,
    ) -> None:
        self._context = _increment_context(context)
        self._preview_counter = preview_counter
        self._refresh_preview()

    def set_input_mode(self, mode: str) -> None:
        self._mode = "incrementing" if mode == "incrementing" else "free"
        if self._mode == "incrementing" and self._rule is None:
            self._rule = _increment_rule()
        self._free_value.setVisible(self._mode == "free")
        self._preview.setVisible(self._mode == "incrementing")
        self._config.setVisible(self._mode == "incrementing")
        self._refresh_preview()

    def clear_value(self) -> None:
        self._free_value.clear()

    def value_text(self) -> str:
        return self._free_value.text().strip() if self._mode == "free" else ""

    def increment_rule(self) -> dict[str, Any] | None:
        if self._mode != "incrementing":
            return None
        return _increment_rule(self._rule)

    def _configure_rule(self) -> None:
        dialog = IncrementRuleDialog(
            self._rule,
            self._context,
            preview_counter=self._preview_counter,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._rule = dialog.rule()
            self._refresh_preview()
            self.changed.emit()

    def _refresh_preview(self) -> None:
        if self._mode != "incrementing":
            return
        counter = self._preview_counter(self._rule) if self._preview_counter else None
        preview, error = _format_increment_preview(self._rule, self._context, counter)
        self._preview.setText(preview if not error else error)


@dataclass(slots=True)
class StepRow:
    """工作流步骤行模型。"""

    step_id: str
    action: str
    view_id: str = "main"
    anchor_id: str | None = None
    value: Any | None = None
    input_mode: str = "free"
    increment_rule: dict[str, Any] | None = None
    wait_seconds: float | None = None
    match_mode: str = "none"
    expected_text: str | list[str] | None = None
    expected_candidates: list[str] | None = None
    timeout_seconds: float | None = None
    poll_interval_seconds: float | None = None
    min_confidence: float | None = None
    ignore_case: bool = False
    normalize_text: bool = False
    requires_confirmation: bool = False


def _parameter_summary(step: StepRow) -> str:
    """生成动作专属参数摘要。

    Args:
        step: 工作流步骤行。

    Returns:
        适合在表格中展示的简短摘要。
    """

    if step.action == "type":
        if step.input_mode == "incrementing":
            rule = _increment_rule(step.increment_rule)
            return f"递增输入：{rule['pattern']}"
        return f"输入：{step.value or '未填写'}"
    if step.action == "hotkey":
        return f"快捷键：{step.value or '未填写'}"
    if step.action == "ocr":
        mode_labels = {
            "contains": "包含",
            "equals": "等于",
            "regex": "正则",
            "not_empty": "非空",
        }
        expected = step.expected_text or step.expected_candidates or "-"
        if isinstance(expected, list):
            expected = " | ".join(str(item) for item in expected)
        timeout = (
            step.timeout_seconds
            if step.timeout_seconds is not None
            else DEFAULT_OCR_TIMEOUT_SECONDS
        )
        poll_interval = (
            step.poll_interval_seconds
            if step.poll_interval_seconds is not None
            else DEFAULT_OCR_POLL_INTERVAL_SECONDS
        )
        return (
            f"{mode_labels.get(step.match_mode, step.match_mode)}：{expected}；"
            f"超时 {timeout:g}s；间隔 {poll_interval:g}s"
        )
    if step.action == "wait":
        duration = (
            step.wait_seconds
            if step.wait_seconds is not None
            else DEFAULT_ACTION_WAIT_SECONDS
        )
        return f"等待 {duration:g}s"
    return "无额外参数"


class ActionParameterDialog(QDialog):
    """根据动作类型编辑步骤专属参数。"""

    def __init__(
        self,
        step: StepRow,
        *,
        context: dict[str, str] | None = None,
        preview_counter: Callable[[dict[str, Any]], int | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """初始化动作参数弹窗。

        Args:
            step: 当前工作流步骤。
            context: 递增输入预览上下文。
            preview_counter: 递增计数预览回调。
            parent: Qt 父组件。
        """

        super().__init__(parent)
        self._step = replace(step)
        self._input_mode: QComboBox | None = None
        self._value_editor: InputValueEditor | None = None
        self._hotkey: QLineEdit | None = None
        self._condition: ConditionEditor | None = None
        self._wait_duration: QDoubleSpinBox | None = None
        self.setWindowTitle("动作参数配置")
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        action_label = dict(ACTION_OPTIONS).get(step.action, step.action)
        form.addRow("动作", QLabel(action_label))

        if step.action == "type":
            self._input_mode = NoWheelComboBox()
            for key, label in INPUT_MODE_OPTIONS:
                self._input_mode.addItem(label, key)
            index = self._input_mode.findData(step.input_mode)
            self._input_mode.setCurrentIndex(max(0, index))
            self._value_editor = InputValueEditor(
                value=step.value,
                input_mode=step.input_mode,
                increment_rule=step.increment_rule,
                context=context,
                preview_counter=preview_counter,
            )
            self._input_mode.currentIndexChanged.connect(
                lambda _index: self._value_editor.set_input_mode(
                    str(self._input_mode.currentData() or "free")
                )
            )
            form.addRow("输入模式", self._input_mode)
            form.addRow("输入内容", self._value_editor)
        elif step.action == "hotkey":
            self._hotkey = QLineEdit(str(step.value or ""))
            self._hotkey.setPlaceholderText("例如：ctrl+v")
            form.addRow("快捷键", self._hotkey)
        elif step.action == "ocr":
            self._condition = ConditionEditor()
            self._condition.set_condition(
                match_mode=step.match_mode,
                expected_text=step.expected_text or step.expected_candidates,
                timeout_seconds=(
                    step.timeout_seconds
                    if step.timeout_seconds is not None
                    else DEFAULT_OCR_TIMEOUT_SECONDS
                ),
                poll_interval_seconds=(
                    step.poll_interval_seconds
                    if step.poll_interval_seconds is not None
                    else DEFAULT_OCR_POLL_INTERVAL_SECONDS
                ),
            )
            form.addRow("OCR条件", self._condition)
        elif step.action == "wait":
            self._wait_duration = NoWheelDoubleSpinBox()
            self._wait_duration.setRange(0, 3600)
            self._wait_duration.setDecimals(1)
            self._wait_duration.setSingleStep(0.5)
            self._wait_duration.setSuffix(" s")
            self._wait_duration.setValue(
                float(
                    step.wait_seconds
                    if step.wait_seconds is not None
                    else DEFAULT_ACTION_WAIT_SECONDS
                )
            )
            form.addRow("等待时长", self._wait_duration)
        else:
            form.addRow("参数", QLabel("该动作没有额外参数"))

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def step(self) -> StepRow:
        """返回应用弹窗配置后的步骤。"""

        step = replace(self._step)
        step.value = None
        step.input_mode = "free"
        step.increment_rule = None
        step.match_mode = "none"
        step.expected_text = None
        step.expected_candidates = None
        step.timeout_seconds = None
        step.poll_interval_seconds = None
        if step.action == "type" and self._input_mode and self._value_editor:
            step.input_mode = str(self._input_mode.currentData() or "free")
            step.value = self._value_editor.value_text() or None
            step.increment_rule = (
                self._value_editor.increment_rule()
                if step.input_mode == "incrementing"
                else None
            )
        elif step.action == "hotkey" and self._hotkey:
            step.value = self._hotkey.text().strip() or None
        elif step.action == "ocr" and self._condition:
            condition = self._condition.condition()
            step.match_mode = str(condition.get("match_mode") or "not_empty")
            step.expected_text = condition.get("expected_text")
            step.expected_candidates = condition.get("expected_candidates")
            step.timeout_seconds = (
                float(condition["timeout_seconds"])
                if condition.get("timeout_seconds") is not None
                else DEFAULT_OCR_TIMEOUT_SECONDS
            )
            step.poll_interval_seconds = (
                float(condition["poll_interval_seconds"])
                if condition.get("poll_interval_seconds") is not None
                else DEFAULT_OCR_POLL_INTERVAL_SECONDS
            )
        elif step.action == "wait" and self._wait_duration:
            step.wait_seconds = float(self._wait_duration.value())
        return step


class WorkflowStepTable(QTableWidget):
    """工作流步骤编辑表格。"""

    rows_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        """初始化步骤表。"""

        super().__init__(0, 10, parent)
        self._anchor_ids: list[str] = []
        self._anchors_by_view: dict[str, list[str]] = {}
        self._view_ids: list[str] = ["main"]
        self._increment_context: dict[str, str] = {}
        self._preview_counter: Callable[[dict[str, Any]], int | None] | None = None
        self.setHorizontalHeaderLabels(
            [
                "步骤 ID",
                "动作",
                "视图",
                "锚点",
                "参数摘要",
                "",
                "动作后等待",
                "",
                "执行前确认",
                "操作",
            ]
        )
        configure_data_table(self, row_height=38)
        interactive_header(self)
        self.setMinimumHeight(120)
        self.setColumnHidden(0, True)
        self.setColumnHidden(5, True)
        self.setColumnHidden(7, True)
        self.setColumnWidth(1, 118)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(3, 180)
        self.setColumnWidth(4, 420)
        self.setColumnWidth(6, 112)
        self.setColumnWidth(8, 86)
        self.setColumnWidth(9, 148)
        self.cellDoubleClicked.connect(self._cell_double_clicked)

    def set_steps(
        self,
        steps: list[StepRow],
        anchor_ids: list[str],
        view_ids: list[str] | None = None,
        *,
        anchors_by_view: dict[str, list[str]] | None = None,
    ) -> None:
        """替换全部步骤。"""

        self._anchor_ids = list(anchor_ids)
        self._view_ids = list(view_ids or ["main"])
        self._anchors_by_view = {
            view_id: list(values)
            for view_id, values in (anchors_by_view or {}).items()
        }
        self.setRowCount(0)
        for step in steps:
            self.add_step(step, anchor_ids, self._view_ids)

    def set_increment_context(
        self,
        context: dict[str, str] | None = None,
        preview_counter: Callable[[dict[str, Any]], int | None] | None = None,
    ) -> None:
        """Set values used to preview incrementing input templates."""

        self._increment_context = dict(context or {})
        self._preview_counter = preview_counter

    def add_step(
        self,
        step: StepRow,
        anchor_ids: list[str],
        view_ids: list[str] | None = None,
    ) -> int:
        """新增步骤行。"""

        if step.wait_seconds is None:
            step = replace(step, wait_seconds=DEFAULT_ACTION_WAIT_SECONDS)
        row = self.rowCount()
        self.insertRow(row)
        self._set_row_model(row, step)
        self.setCellWidget(row, 1, self._action_combo(step.action))
        self.setCellWidget(row, 2, self._view_combo(view_ids or ["main"], step.view_id))
        self.setCellWidget(
            row,
            3,
            self._anchor_combo(self._anchor_ids_for_view(step.view_id), step.anchor_id),
        )
        self._set_parameter_summary(row, step)
        wait = NoWheelDoubleSpinBox()
        wait.setObjectName("TableSpinBox")
        set_embedded_editor_height(wait)
        wait.setRange(0, 3600)
        wait.setDecimals(1)
        wait.setSingleStep(0.5)
        wait.setSuffix(" s")
        wait.setValue(
            0.0
            if step.action == "wait"
            else float(step.wait_seconds)
        )
        wait.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(row, 6, wait)
        confirm = self._checkbox(step.requires_confirmation)
        self.setCellWidget(row, 8, confirm)
        self.setCellWidget(row, 9, self._row_buttons(row))
        self._sync_action_controls(row)
        self.rows_changed.emit()
        return row

    def insert_action(self, row: int | None = None) -> None:
        """插入普通动作步骤。

        Args:
            row: 插入位置；为空或小于 0 时追加到末尾。
        """

        target = self.rowCount() if row is None or row < 0 else row
        view_id = self._view_ids[0] if self._view_ids else "main"
        view_anchor_ids = self._anchor_ids_for_view(view_id)
        anchor_id = view_anchor_ids[0] if view_anchor_ids else None
        rows = self.rows()
        rows.insert(
            target,
            StepRow(
                step_id=self._next_step_id("step"),
                action="click",
                view_id=view_id,
                anchor_id=anchor_id,
                wait_seconds=DEFAULT_ACTION_WAIT_SECONDS,
                match_mode="none",
            ),
        )
        self.set_steps(
            rows,
            self._anchor_ids,
            self._view_ids,
            anchors_by_view=self._anchors_by_view,
        )
        self.selectRow(target)

    def insert_wait(self, row: int | None = None) -> None:
        """插入等待步骤。"""

        target = self.rowCount() if row is None or row < 0 else row
        rows = self.rows()
        rows.insert(
            target,
            StepRow(
                step_id=self._next_step_id("wait"),
                action="wait",
                wait_seconds=DEFAULT_ACTION_WAIT_SECONDS,
            ),
        )
        self.set_steps(
            rows,
            self._anchor_ids,
            self._view_ids,
            anchors_by_view=self._anchors_by_view,
        )
        self.selectRow(target)

    def rows(self) -> list[StepRow]:
        """返回全部步骤行模型。"""

        result: list[StepRow] = []
        for row in range(self.rowCount()):
            stored = self._row_model(row)
            if stored is None:
                continue
            action = self._combo_data(row, 1) or "click"
            view_id = self._combo_data(row, 2) or "main"
            anchor_id = self._combo_data(row, 3) or None
            confirm = self._checkbox_value(row, 8)
            wait_seconds = (
                stored.wait_seconds
                if action == "wait"
                else self._spin_value(row, 6)
            )
            result.append(
                replace(
                    stored,
                    action=action,
                    view_id="main" if action == "wait" else str(view_id),
                    anchor_id=None if action == "wait" else anchor_id,
                    wait_seconds=(
                        float(wait_seconds)
                        if wait_seconds is not None
                        else DEFAULT_ACTION_WAIT_SECONDS
                    ),
                    requires_confirmation=bool(confirm),
                )
            )
        return result

    def _action_combo(self, action: str) -> QComboBox:
        """创建动作下拉框。"""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        for key, label in ACTION_OPTIONS:
            combo.addItem(label, key)
        index = combo.findData(action)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda _idx, c=combo: self._action_changed(c))
        return combo

    def _view_combo(self, view_ids: list[str], view_id: str | None) -> QComboBox:
        """创建视图下拉框。"""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        for item in view_ids or ["main"]:
            combo.addItem(item, item)
        index = combo.findData(view_id or "main")
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda _idx, c=combo: self._view_changed(c))
        return combo

    def _anchor_combo(self, anchor_ids: list[str], anchor_id: str | None) -> QComboBox:
        """创建锚点下拉框。"""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        combo.addItem("", "")
        for item in anchor_ids:
            combo.addItem(item, item)
        index = combo.findData(anchor_id or "")
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda _idx: self.rows_changed.emit())
        return combo

    def _anchor_ids_for_view(self, view_id: str | None) -> list[str]:
        """Return anchors available in the selected view."""

        if not self._anchors_by_view:
            return list(self._anchor_ids)
        return list(self._anchors_by_view.get(view_id or "main", []))

    def _view_changed(self, combo: QComboBox) -> None:
        """Refresh the row anchor choices when its view changes."""

        row = self.indexAt(combo.pos()).row()
        if row >= 0:
            self._refresh_anchor_combo(row)
            self.rows_changed.emit()

    def _refresh_anchor_combo(self, row: int) -> None:
        """Rebuild a row's anchor combo for its selected view."""

        current = self._combo_data(row, 3)
        view_id = self._combo_data(row, 2) or "main"
        anchor_ids = self._anchor_ids_for_view(str(view_id))
        anchor_id = str(current) if current in anchor_ids else None
        self.setCellWidget(row, 3, self._anchor_combo(anchor_ids, anchor_id))

    def _checkbox(self, checked: bool) -> QCheckBox:
        """创建表格内复选框。

        Args:
            checked: 初始勾选状态。

        Returns:
            可编辑的确认复选框。
        """

        checkbox = TableCheckBox()
        checkbox.setObjectName("TableCheck")
        set_embedded_editor_height(checkbox)
        checkbox.setChecked(checked)
        checkbox.toggled.connect(lambda _checked: self.rows_changed.emit())
        return checkbox

    def _row_buttons(self, row: int) -> QWidget:
        """创建行操作按钮。"""

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for label, tooltip, danger, callback in [
            (
                "配置",
                "配置动作参数",
                False,
                lambda _checked=False, r=row: self._configure_parameters(r),
            ),
            ("↑", "上移", False, lambda _checked=False, r=row: self._move_row(r, -1)),
            ("↓", "下移", False, lambda _checked=False, r=row: self._move_row(r, 1)),
            ("×", "删除", True, lambda _checked=False, r=row: self._delete_row(r)),
        ]:
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.setObjectName("TableDanger" if danger else "TableAction")
            button.setFixedSize(46 if label == "配置" else 22, 22)
            button.clicked.connect(callback)
            layout.addWidget(button)
        return widget

    def _action_changed(self, combo: QComboBox) -> None:
        """动作变化时同步控件启用状态。"""

        row = self.indexAt(combo.pos()).row()
        if row >= 0:
            stored = self._row_model(row)
            action = str(combo.currentData() or "click")
            if stored is not None and action != stored.action:
                previous_action = stored.action
                current_wait = (
                    stored.wait_seconds
                    if previous_action == "wait"
                    else self._spin_value(row, 6)
                )
                current = replace(
                    stored,
                    view_id=str(self._combo_data(row, 2) or "main"),
                    anchor_id=self._combo_data(row, 3) or None,
                    wait_seconds=(
                        float(current_wait)
                        if current_wait is not None
                        else DEFAULT_ACTION_WAIT_SECONDS
                    ),
                    requires_confirmation=self._checkbox_value(row, 8),
                )
                self._set_row_model(row, self._step_for_action(current, action))
                if action == "wait":
                    view = self.cellWidget(row, 2)
                    if isinstance(view, QComboBox):
                        index = view.findData("main")
                        view.setCurrentIndex(max(0, index))
                    self.setCellWidget(row, 3, self._anchor_combo([], None))
                elif previous_action == "wait":
                    self._refresh_anchor_combo(row)
            self._sync_action_controls(row)
            self.rows_changed.emit()

    def _sync_action_controls(self, row: int) -> None:
        """根据动作启用或禁用行控件。"""

        action = str(self._combo_data(row, 1) or "click")
        is_wait = action == "wait"
        for column in (2, 3):
            widget = self.cellWidget(row, column)
            if widget is not None:
                widget.setEnabled(not is_wait)
        wait = self.cellWidget(row, 6)
        if isinstance(wait, QDoubleSpinBox):
            wait.setEnabled(not is_wait)
            if is_wait:
                wait.setValue(0.0)
            else:
                stored = self._row_model(row)
                wait.setValue(
                    float(
                        stored.wait_seconds
                        if stored is not None and stored.wait_seconds is not None
                        else DEFAULT_ACTION_WAIT_SECONDS
                    )
                )
        stored = self._row_model(row)
        if stored is not None:
            self._set_parameter_summary(row, stored)

    def _cell_double_clicked(self, row: int, column: int) -> None:
        """双击参数摘要单元格时打开动作参数配置弹窗。

        Args:
            row: 被双击的表格行号。
            column: 被双击的表格列号。
        """

        if column == 4:
            self._configure_parameters(row)

    def _configure_parameters(self, row: int) -> None:
        """打开指定步骤的动作参数配置弹窗。

        Args:
            row: 待配置的表格行号。
        """

        step = self._current_step(row)
        if step is None:
            return
        dialog = ActionParameterDialog(
            step,
            context=self._increment_context,
            preview_counter=self._preview_counter,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.step()
        self._set_row_model(row, updated)
        self._set_parameter_summary(row, updated)
        self.rows_changed.emit()

    def _current_step(self, row: int) -> StepRow | None:
        """合并行控件和隐藏模型，返回当前步骤。"""

        stored = self._row_model(row)
        if stored is None:
            return None
        action = str(self._combo_data(row, 1) or stored.action)
        wait_seconds = (
            stored.wait_seconds
            if action == "wait"
            else self._spin_value(row, 6)
        )
        return replace(
            stored,
            action=action,
            view_id=(
                "main"
                if action == "wait"
                else str(self._combo_data(row, 2) or "main")
            ),
            anchor_id=(
                None
                if action == "wait"
                else self._combo_data(row, 3) or None
            ),
            wait_seconds=(
                float(wait_seconds)
                if wait_seconds is not None
                else DEFAULT_ACTION_WAIT_SECONDS
            ),
            requires_confirmation=self._checkbox_value(row, 8),
        )

    @staticmethod
    def _step_for_action(step: StepRow, action: str) -> StepRow:
        """切换动作时清理不适用参数并生成默认配置。"""

        wait_seconds = (
            step.wait_seconds
            if step.action != "wait" and action != "wait"
            else DEFAULT_ACTION_WAIT_SECONDS
        )
        updated = StepRow(
            step_id=step.step_id,
            action=action,
            view_id="main" if action == "wait" else step.view_id,
            anchor_id=None if action == "wait" else step.anchor_id,
            wait_seconds=wait_seconds,
            requires_confirmation=step.requires_confirmation,
        )
        if action == "ocr":
            updated.match_mode = "not_empty"
            updated.timeout_seconds = DEFAULT_OCR_TIMEOUT_SECONDS
            updated.poll_interval_seconds = DEFAULT_OCR_POLL_INTERVAL_SECONDS
        return updated

    def _set_row_model(self, row: int, step: StepRow) -> None:
        """保存步骤行隐藏模型。"""

        item = self.item(row, 0) or QTableWidgetItem()
        item.setText(step.step_id)
        item.setData(Qt.ItemDataRole.UserRole, step)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 0, item)

    def _row_model(self, row: int) -> StepRow | None:
        """读取步骤行隐藏模型。"""

        item = self.item(row, 0)
        if item is None:
            return None
        model = item.data(Qt.ItemDataRole.UserRole)
        return model if isinstance(model, StepRow) else None

    def _set_parameter_summary(self, row: int, step: StepRow) -> None:
        """刷新步骤参数摘要。"""

        summary = _parameter_summary(step)
        item = self.item(row, 4) or QTableWidgetItem()
        item.setText(summary)
        item.setToolTip(summary)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 4, item)

    def _move_row(self, row: int, delta: int) -> None:
        """移动行。"""

        target = row + delta
        if row < 0 or target < 0 or target >= self.rowCount():
            return
        rows = self.rows()
        rows[row], rows[target] = rows[target], rows[row]
        self.set_steps(
            rows,
            self._anchor_ids,
            self._view_ids,
            anchors_by_view=self._anchors_by_view,
        )
        self.selectRow(target)

    def _delete_row(self, row: int) -> None:
        """删除行。"""

        if 0 <= row < self.rowCount():
            self.removeRow(row)
            self._rebind_buttons()
            self.rows_changed.emit()

    def _rebind_buttons(self) -> None:
        """重新绑定行按钮。"""

        for row in range(self.rowCount()):
            self.setCellWidget(row, 9, self._row_buttons(row))

    def _next_step_id(self, prefix: str) -> str:
        """生成步骤 ID。"""

        existing = {
            self.item(row, 0).text().strip()
            for row in range(self.rowCount())
            if self.item(row, 0)
        }
        index = 1
        while f"{prefix}_{index}" in existing:
            index += 1
        return f"{prefix}_{index}"

    def _combo_data(self, row: int, column: int):
        """读取下拉框数据。"""

        widget = self.cellWidget(row, column)
        return widget.currentData() if isinstance(widget, QComboBox) else None

    def _checkbox_value(self, row: int, column: int) -> bool:
        """读取复选框状态。"""

        widget = self.cellWidget(row, column)
        return widget.isChecked() if isinstance(widget, QCheckBox) else False

    def _spin_value(self, row: int, column: int) -> float | None:
        """读取数字框内容。"""

        widget = self.cellWidget(row, column)
        return widget.value() if isinstance(widget, QDoubleSpinBox) else None
