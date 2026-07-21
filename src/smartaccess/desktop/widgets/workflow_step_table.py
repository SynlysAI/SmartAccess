"""工作流步骤表格组件。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from string import Formatter
import re
from typing import Any, Callable

from PyQt6.QtCore import pyqtSignal
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
    min_confidence: float | None = None
    ignore_case: bool = False
    normalize_text: bool = False
    requires_confirmation: bool = False


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
                "值",
                "输入模式",
                "等待",
                "OCR配置",
                "执行前确认",
                "操作",
            ]
        )
        configure_data_table(self, row_height=38)
        interactive_header(self)
        self.setMinimumHeight(120)
        self.setColumnWidth(0, 80)
        self.setColumnWidth(1, 118)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(3, 180)
        self.setColumnWidth(4, 260)
        self.setColumnWidth(5, 110)
        self.setColumnWidth(6, 100)
        self.setColumnWidth(7, 360)
        self.setColumnWidth(8, 86)
        self.setColumnWidth(9, 104)

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
        for row in range(self.rowCount()):
            value = self.cellWidget(row, 4)
            if isinstance(value, InputValueEditor):
                value.set_context(self._increment_context, self._preview_counter)

    def add_step(
        self,
        step: StepRow,
        anchor_ids: list[str],
        view_ids: list[str] | None = None,
    ) -> int:
        """新增步骤行。"""

        row = self.rowCount()
        self.insertRow(row)
        self.setItem(row, 0, QTableWidgetItem(step.step_id))
        self.setCellWidget(row, 1, self._action_combo(step.action))
        self.setCellWidget(row, 2, self._view_combo(view_ids or ["main"], step.view_id))
        self.setCellWidget(
            row,
            3,
            self._anchor_combo(self._anchor_ids_for_view(step.view_id), step.anchor_id),
        )
        value = InputValueEditor(
            value=step.value,
            input_mode=step.input_mode,
            increment_rule=step.increment_rule,
            context=self._increment_context,
            preview_counter=self._preview_counter,
        )
        value.changed.connect(lambda: self.rows_changed.emit())
        self.setCellWidget(row, 4, value)
        self.setCellWidget(row, 5, self._input_mode_combo(step.input_mode))
        wait = NoWheelDoubleSpinBox()
        wait.setObjectName("TableSpinBox")
        set_embedded_editor_height(wait)
        wait.setRange(0, 3600)
        wait.setDecimals(1)
        wait.setSingleStep(0.5)
        wait.setSuffix(" s")
        wait.setValue(float(step.wait_seconds or (1.0 if step.action == "wait" else 0)))
        wait.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(row, 6, wait)
        condition = ConditionEditor()
        condition.set_condition(
            match_mode=step.match_mode,
            expected_text=step.expected_text or step.expected_candidates,
            timeout_seconds=step.timeout_seconds,
            min_confidence=step.min_confidence,
            ignore_case=step.ignore_case,
            normalize_text=step.normalize_text,
        )
        condition.match_mode.currentIndexChanged.connect(lambda _idx: self.rows_changed.emit())
        condition.expected_text.textChanged.connect(lambda _text: self.rows_changed.emit())
        condition.timeout_seconds.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(row, 7, condition)
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
        self.insertRow(target)
        self.setItem(target, 0, QTableWidgetItem(self._next_step_id("wait")))
        self.setCellWidget(target, 1, self._action_combo("wait"))
        self.setCellWidget(target, 2, self._view_combo(self._view_ids, "main"))
        self.setCellWidget(target, 3, self._anchor_combo([], None))
        value = InputValueEditor(context=self._increment_context)
        value.setEnabled(False)
        self.setCellWidget(target, 4, value)
        mode = self._input_mode_combo("free")
        mode.setEnabled(False)
        self.setCellWidget(target, 5, mode)
        wait = NoWheelDoubleSpinBox()
        wait.setObjectName("TableSpinBox")
        set_embedded_editor_height(wait)
        wait.setRange(0, 3600)
        wait.setDecimals(1)
        wait.setValue(1.0)
        wait.setSuffix(" s")
        wait.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(target, 6, wait)
        condition = ConditionEditor()
        condition.setEnabled(False)
        self.setCellWidget(target, 7, condition)
        confirm = self._checkbox(False)
        self.setCellWidget(target, 8, confirm)
        self._rebind_buttons()
        self.rows_changed.emit()

    def rows(self) -> list[StepRow]:
        """返回全部步骤行模型。"""

        result: list[StepRow] = []
        for row in range(self.rowCount()):
            step_id = self.item(row, 0).text().strip() if self.item(row, 0) else ""
            action = self._combo_data(row, 1) or "click"
            view_id = self._combo_data(row, 2) or "main"
            anchor_id = self._combo_data(row, 3) or None
            value_text = self._value_text(row, 4)
            input_mode = self._combo_data(row, 5) or "free"
            wait_seconds = self._spin_value(row, 6)
            condition = self.cellWidget(row, 7)
            condition_data = (
                condition.condition()
                if action == "ocr" and isinstance(condition, ConditionEditor)
                else {
                    "match_mode": "none",
                    "expected_text": None,
                    "expected_candidates": None,
                    "timeout_seconds": None,
                    "min_confidence": None,
                    "ignore_case": True,
                    "normalize_text": True,
                }
            )
            confirm = self._checkbox_value(row, 8)
            normalized_input_mode = str(input_mode) if action == "type" else "free"
            increment_rule = (
                self._increment_rule(row, 4)
                if normalized_input_mode == "incrementing"
                else None
            )
            result.append(
                StepRow(
                    step_id=step_id or self._next_step_id("step"),
                    action=action,
                    view_id="main" if action == "wait" else str(view_id),
                    anchor_id=None if action == "wait" else anchor_id,
                    value=value_text or None,
                    input_mode=normalized_input_mode,
                    increment_rule=increment_rule,
                    wait_seconds=wait_seconds if action == "wait" or wait_seconds else None,
                    match_mode=str(condition_data.get("match_mode") or "none"),
                    expected_text=condition_data.get("expected_text"),
                    expected_candidates=condition_data.get("expected_candidates"),
                    timeout_seconds=condition_data.get("timeout_seconds"),
                    min_confidence=condition_data.get("min_confidence"),
                    ignore_case=bool(condition_data.get("ignore_case")),
                    normalize_text=bool(condition_data.get("normalize_text")),
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

    def _input_mode_combo(self, input_mode: str) -> QComboBox:
        """Create the input mode selector."""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        for key, label in INPUT_MODE_OPTIONS:
            combo.addItem(label, key)
        index = combo.findData(input_mode or "free")
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda _idx, c=combo: self._input_mode_changed(c))
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
            ("↑", "上移", False, lambda _checked=False, r=row: self._move_row(r, -1)),
            ("↓", "下移", False, lambda _checked=False, r=row: self._move_row(r, 1)),
            ("×", "删除", True, lambda _checked=False, r=row: self._delete_row(r)),
        ]:
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.setObjectName("TableDanger" if danger else "TableAction")
            button.setFixedSize(22, 22)
            button.clicked.connect(callback)
            layout.addWidget(button)
        return widget

    def _action_changed(self, combo: QComboBox) -> None:
        """动作变化时同步控件启用状态。"""

        row = self.indexAt(combo.pos()).row()
        if row >= 0:
            self._sync_action_controls(row)
            self.rows_changed.emit()

    def _input_mode_changed(self, combo: QComboBox) -> None:
        """Sync the row value editor when input mode changes."""

        row = self.indexAt(combo.pos()).row()
        if row >= 0:
            self._sync_action_controls(row)
            self.rows_changed.emit()

    def _sync_action_controls(self, row: int) -> None:
        """根据动作启用或禁用行控件。"""

        action = self._combo_data(row, 1)
        is_wait = action == "wait"
        is_ocr = action == "ocr"
        is_type = action == "type"
        disable_value = is_wait or is_ocr
        value_widget = self.cellWidget(row, 4)
        if value_widget is not None:
            value_widget.setEnabled(not disable_value)
        mode = self.cellWidget(row, 5)
        if mode is not None:
            mode.setEnabled(is_type and not disable_value)
            if not is_type and isinstance(mode, QComboBox):
                index = mode.findData("free")
                mode.setCurrentIndex(max(0, index))
        value = self.cellWidget(row, 4)
        if isinstance(value, InputValueEditor):
            input_mode = self._combo_data(row, 5) if is_type and not disable_value else "free"
            value.set_input_mode(str(input_mode or "free"))
        for column in (2, 3):
            widget = self.cellWidget(row, column)
            if widget is not None:
                widget.setEnabled(True)
        condition = self.cellWidget(row, 7)
        if condition is not None:
            condition.setEnabled(is_ocr)
        wait = self.cellWidget(row, 6)
        if wait is not None:
            wait.setEnabled(True)
        if is_wait or is_ocr:
            value = self.cellWidget(row, 4)
            if isinstance(value, InputValueEditor):
                value.clear_value()
            if is_ocr and isinstance(condition, ConditionEditor):
                if condition.match_mode.currentData() == "none":
                    index = condition.match_mode.findData("not_empty")
                    condition.match_mode.setCurrentIndex(max(0, index))
        if not is_ocr and isinstance(condition, ConditionEditor):
            none_index = condition.match_mode.findData("none")
            condition.match_mode.setCurrentIndex(max(0, none_index))
            condition.expected_text.clear()
            condition.timeout_seconds.setValue(0.0)

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

    def _line_text(self, row: int, column: int) -> str:
        """读取文本框内容。"""

        widget = self.cellWidget(row, column)
        return widget.text().strip() if isinstance(widget, QLineEdit) else ""

    def _value_text(self, row: int, column: int) -> str:
        """Read the value editor text."""

        widget = self.cellWidget(row, column)
        return widget.value_text() if isinstance(widget, InputValueEditor) else ""

    def _increment_rule(self, row: int, column: int) -> dict[str, Any]:
        """Read the row's incrementing input rule."""

        widget = self.cellWidget(row, column)
        if isinstance(widget, InputValueEditor):
            return widget.increment_rule() or _increment_rule()
        return _increment_rule()

    def _spin_value(self, row: int, column: int) -> float | None:
        """读取数字框内容。"""

        widget = self.cellWidget(row, column)
        return widget.value() if isinstance(widget, QDoubleSpinBox) else None
