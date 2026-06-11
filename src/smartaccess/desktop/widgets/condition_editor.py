"""Simplified OCR expectation editor for workflow steps."""

from __future__ import annotations

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

_MATCH_MODES = ("none", "contains", "equals", "regex", "not_empty")


class ConditionEditorDialog(QDialog):
    """Modal dialog for editing post-action OCR expectations."""

    def __init__(
        self,
        condition: dict | None,
        *,
        available_sources: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑 OCR 期望")
        self.setMinimumWidth(380)
        self._condition = condition or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel("配置动作执行后的 OCR 期望；固定等待请在步骤 wait_seconds 中设置。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b95a8;font-size:12px;padding:4px 0;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        self._match_mode = QComboBox()
        self._match_mode.setMinimumHeight(32)
        for mode in _MATCH_MODES:
            self._match_mode.addItem(mode)
        current_mode = str(self._condition.get("match_mode") or "none")
        idx = self._match_mode.findText(current_mode)
        if idx >= 0:
            self._match_mode.setCurrentIndex(idx)
        form.addRow("match_mode", self._match_mode)

        self._expected = QLineEdit()
        self._expected.setPlaceholderText("例如 Running、4.20")
        self._expected.setText(str(self._condition.get("expected_text") or ""))
        form.addRow("expected_text", self._expected)

        self._timeout = QDoubleSpinBox()
        self._timeout.setRange(0.1, 3600.0)
        self._timeout.setDecimals(1)
        self._timeout.setSuffix(" 秒")
        self._timeout.setValue(float(self._condition.get("timeout_seconds") or 10.0))
        form.addRow("timeout_seconds", self._timeout)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        save = QPushButton("保存")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

    def condition_dict(self) -> dict:
        """Return simplified OCR expectation fields."""

        match_mode = self._match_mode.currentText()
        if match_mode == "none":
            return {"match_mode": "none"}
        result: dict = {
            "match_mode": match_mode,
            "timeout_seconds": self._timeout.value(),
        }
        expected = self._expected.text().strip()
        if match_mode != "not_empty":
            result["expected_text"] = expected
        return result
