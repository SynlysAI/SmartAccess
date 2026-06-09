"""Condition editor dialog for workflow steps.

Provides a focused form for editing :class:`WorkflowStep.condition`:
source, observation mode, operator, expected value, timeout, and poll interval.
All time fields are in seconds with explicit labeling.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartaccess.shared.contracts.workflow import normalize_condition

_OBSERVATION_MODES = ["ocr", "template", "presence", "color"]
_OPERATORS = ["exists", "equals", "contains", "not_empty"]


class ConditionEditorDialog(QDialog):
    """Modal dialog for editing a step's observation condition."""

    def __init__(
        self,
        condition: dict | None,
        *,
        available_sources: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑观测条件")
        self.setMinimumWidth(420)
        self._condition = normalize_condition(condition) or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(
            "配置步骤完成后如何观测结果。\n"
            "超时与轮询间隔均以<strong>秒</strong>为单位。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b95a8;font-size:12px;padding:4px 0;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        # Source
        self._source = QComboBox()
        self._source.setEditable(True)
        self._source.setMinimumHeight(32)
        sources = available_sources or []
        for s in sources:
            self._source.addItem(s)
        current_source = self._condition.get("source", "")
        if current_source:
            idx = self._source.findText(current_source)
            if idx >= 0:
                self._source.setCurrentIndex(idx)
            else:
                self._source.setEditText(current_source)
        form.addRow("观测来源 (source)", self._source)

        # Mode
        self._mode = QComboBox()
        self._mode.setMinimumHeight(32)
        for m in _OBSERVATION_MODES:
            self._mode.addItem(m)
        current_mode = self._condition.get("mode", "ocr")
        idx = self._mode.findText(current_mode)
        if idx >= 0:
            self._mode.setCurrentIndex(idx)
        form.addRow("识别模式 (mode)", self._mode)

        # Operator
        self._operator = QComboBox()
        self._operator.setMinimumHeight(32)
        for op in _OPERATORS:
            self._operator.addItem(op)
        current_op = self._condition.get("operator", "exists")
        idx = self._operator.findText(current_op)
        if idx >= 0:
            self._operator.setCurrentIndex(idx)
        form.addRow("比较运算符 (operator)", self._operator)

        # Expected value
        self._expected = QLineEdit()
        self._expected.setPlaceholderText("期望值，如 Running、4.20")
        self._expected.setText(str(self._condition.get("expected", "")))
        form.addRow("期望值 (expected)", self._expected)

        # Timeout
        self._timeout = QDoubleSpinBox()
        self._timeout.setRange(0.1, 3600.0)
        self._timeout.setDecimals(1)
        self._timeout.setSuffix(" 秒")
        self._timeout.setValue(float(self._condition.get("timeout_seconds", 30.0)))
        self._timeout.setToolTip("超时时间，单位为秒。超时后视为条件不满足。")
        form.addRow("超时 (timeout_seconds)", self._timeout)

        # Poll interval
        self._poll_interval = QDoubleSpinBox()
        self._poll_interval.setRange(0.1, 60.0)
        self._poll_interval.setDecimals(1)
        self._poll_interval.setSuffix(" 秒")
        self._poll_interval.setValue(float(self._condition.get("poll_interval_seconds", 1.0)))
        self._poll_interval.setToolTip("轮询间隔，单位为秒。每隔 N 秒检查一次条件。")
        form.addRow("轮询间隔 (poll_interval_seconds)", self._poll_interval)

        layout.addLayout(form)
        layout.addSpacing(8)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        save = QPushButton("保存条件")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

    def condition_dict(self) -> dict:
        """Return the edited condition as a dict suitable for WorkflowStep.condition."""
        return {
            "source": self._source.currentText().strip(),
            "mode": self._mode.currentText(),
            "operator": self._operator.currentText(),
            "expected": self._expected.text().strip(),
            "timeout_seconds": self._timeout.value(),
            "poll_interval_seconds": self._poll_interval.value(),
        }
