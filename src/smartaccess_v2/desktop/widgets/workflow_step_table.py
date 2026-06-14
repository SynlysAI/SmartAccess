"""工作流步骤表格组件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from smartaccess_v2.desktop.widgets.condition_editor import ConditionEditor
from smartaccess_v2.desktop.widgets.table_style import (
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
    ("wait", "等待"),
]


@dataclass(slots=True)
class StepRow:
    """工作流步骤行模型。"""

    step_id: str
    action: str
    anchor_id: str | None = None
    value: Any | None = None
    wait_seconds: float | None = None
    match_mode: str = "none"
    expected_text: str | None = None
    timeout_seconds: float | None = None
    requires_confirmation: bool = False


class WorkflowStepTable(QTableWidget):
    """工作流步骤编辑表格。"""

    rows_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        """初始化步骤表。"""

        super().__init__(0, 8, parent)
        self._anchor_ids: list[str] = []
        self.setHorizontalHeaderLabels(
            ["步骤 ID", "动作", "锚点", "值", "等待", "OCR 条件", "确认", "操作"]
        )
        configure_data_table(self, row_height=38)
        interactive_header(self)
        self.setMinimumHeight(120)
        self.setColumnWidth(0, 80)
        self.setColumnWidth(1, 118)
        self.setColumnWidth(2, 180)
        self.setColumnWidth(3, 170)
        self.setColumnWidth(4, 108)
        self.setColumnWidth(5, 360)
        self.setColumnWidth(6, 50)
        self.setColumnWidth(7, 104)

    def set_steps(self, steps: list[StepRow], anchor_ids: list[str]) -> None:
        """替换全部步骤。"""

        self._anchor_ids = list(anchor_ids)
        self.setRowCount(0)
        for step in steps:
            self.add_step(step, anchor_ids)

    def add_step(self, step: StepRow, anchor_ids: list[str]) -> int:
        """新增步骤行。"""

        row = self.rowCount()
        self.insertRow(row)
        self.setItem(row, 0, QTableWidgetItem(step.step_id))
        self.setCellWidget(row, 1, self._action_combo(step.action))
        self.setCellWidget(row, 2, self._anchor_combo(anchor_ids, step.anchor_id))
        value = QLineEdit("" if step.value is None else str(step.value))
        set_embedded_editor_height(value)
        value.textChanged.connect(lambda _text: self.rows_changed.emit())
        self.setCellWidget(row, 3, value)
        wait = NoWheelDoubleSpinBox()
        wait.setObjectName("TableSpinBox")
        set_embedded_editor_height(wait)
        wait.setRange(0, 3600)
        wait.setDecimals(1)
        wait.setSingleStep(0.5)
        wait.setSuffix(" s")
        wait.setValue(float(step.wait_seconds or (1.0 if step.action == "wait" else 0)))
        wait.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(row, 4, wait)
        condition = ConditionEditor()
        condition.set_condition(
            match_mode=step.match_mode,
            expected_text=step.expected_text,
            timeout_seconds=step.timeout_seconds,
        )
        condition.match_mode.currentIndexChanged.connect(lambda _idx: self.rows_changed.emit())
        condition.expected_text.textChanged.connect(lambda _text: self.rows_changed.emit())
        condition.timeout_seconds.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(row, 5, condition)
        confirm = self._checkbox(step.requires_confirmation)
        self.setCellWidget(row, 6, confirm)
        self.setCellWidget(row, 7, self._row_buttons(row))
        self._sync_action_controls(row)
        self.rows_changed.emit()
        return row

    def insert_action(self, row: int | None = None) -> None:
        """插入普通动作步骤。

        Args:
            row: 插入位置；为空或小于 0 时追加到末尾。
        """

        target = self.rowCount() if row is None or row < 0 else row
        anchor_id = self._anchor_ids[0] if self._anchor_ids else None
        rows = self.rows()
        rows.insert(
            target,
            StepRow(
                step_id=self._next_step_id("step"),
                action="click",
                anchor_id=anchor_id,
                match_mode="none",
            ),
        )
        self.set_steps(rows, self._anchor_ids)
        self.selectRow(target)

    def insert_wait(self, row: int | None = None) -> None:
        """插入等待步骤。"""

        target = self.rowCount() if row is None or row < 0 else row
        self.insertRow(target)
        self.setItem(target, 0, QTableWidgetItem(self._next_step_id("wait")))
        self.setCellWidget(target, 1, self._action_combo("wait"))
        self.setCellWidget(target, 2, self._anchor_combo([], None))
        value = QLineEdit("")
        set_embedded_editor_height(value)
        value.setEnabled(False)
        self.setCellWidget(target, 3, value)
        wait = NoWheelDoubleSpinBox()
        wait.setObjectName("TableSpinBox")
        set_embedded_editor_height(wait)
        wait.setRange(0, 3600)
        wait.setDecimals(1)
        wait.setValue(1.0)
        wait.setSuffix(" s")
        wait.valueChanged.connect(lambda _value: self.rows_changed.emit())
        self.setCellWidget(target, 4, wait)
        condition = ConditionEditor()
        condition.setEnabled(False)
        self.setCellWidget(target, 5, condition)
        confirm = self._checkbox(False)
        confirm.setEnabled(False)
        self.setCellWidget(target, 6, confirm)
        self._rebind_buttons()
        self.rows_changed.emit()

    def rows(self) -> list[StepRow]:
        """返回全部步骤行模型。"""

        result: list[StepRow] = []
        for row in range(self.rowCount()):
            step_id = self.item(row, 0).text().strip() if self.item(row, 0) else ""
            action = self._combo_data(row, 1) or "click"
            anchor_id = self._combo_data(row, 2) or None
            value_text = self._line_text(row, 3)
            wait_seconds = self._spin_value(row, 4)
            condition = self.cellWidget(row, 5)
            condition_data = (
                condition.condition() if isinstance(condition, ConditionEditor) else {}
            )
            confirm = self._checkbox_value(row, 6)
            result.append(
                StepRow(
                    step_id=step_id or self._next_step_id("step"),
                    action=action,
                    anchor_id=None if action == "wait" else anchor_id,
                    value=value_text or None,
                    wait_seconds=wait_seconds if action == "wait" or wait_seconds else None,
                    match_mode=str(condition_data.get("match_mode") or "none"),
                    expected_text=condition_data.get("expected_text"),
                    timeout_seconds=condition_data.get("timeout_seconds"),
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

    def _sync_action_controls(self, row: int) -> None:
        """根据动作启用或禁用行控件。"""

        is_wait = self._combo_data(row, 1) == "wait"
        for column in (2, 3, 5, 6):
            widget = self.cellWidget(row, column)
            if widget is not None:
                widget.setEnabled(not is_wait)
        wait = self.cellWidget(row, 4)
        if wait is not None:
            wait.setEnabled(True)
        if is_wait:
            anchor = self.cellWidget(row, 2)
            if isinstance(anchor, QComboBox):
                anchor.setCurrentIndex(0)
            value = self.cellWidget(row, 3)
            if isinstance(value, QLineEdit):
                value.clear()
            confirm = self.cellWidget(row, 6)
            if isinstance(confirm, QCheckBox):
                confirm.setChecked(False)

    def _move_row(self, row: int, delta: int) -> None:
        """移动行。"""

        target = row + delta
        if row < 0 or target < 0 or target >= self.rowCount():
            return
        rows = self.rows()
        rows[row], rows[target] = rows[target], rows[row]
        self.set_steps(rows, self._anchor_ids)
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
            self.setCellWidget(row, 7, self._row_buttons(row))

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

    def _spin_value(self, row: int, column: int) -> float | None:
        """读取数字框内容。"""

        widget = self.cellWidget(row, column)
        return widget.value() if isinstance(widget, QDoubleSpinBox) else None
