"""工作流 OCR 条件编辑器。"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QWidget

from smartaccess_v2.desktop.widgets.table_style import set_embedded_editor_height


class ConditionEditor(QWidget):
    """编辑工作流步骤 OCR 期望条件。"""

    def __init__(self, parent=None) -> None:
        """初始化条件编辑器。"""

        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.match_mode = QComboBox()
        self.match_mode.setObjectName("ConditionMode")
        set_embedded_editor_height(self.match_mode)
        for key, label in [
            ("none", "无"),
            ("contains", "包含"),
            ("equals", "等于"),
            ("regex", "正则"),
            ("not_empty", "非空"),
        ]:
            self.match_mode.addItem(label, key)
        self.expected_text = QLineEdit()
        self.expected_text.setObjectName("ConditionText")
        self.expected_text.setPlaceholderText("期望文本")
        set_embedded_editor_height(self.expected_text)
        self.timeout_seconds = QDoubleSpinBox()
        self.timeout_seconds.setObjectName("ConditionTimeout")
        set_embedded_editor_height(self.timeout_seconds)
        self.timeout_seconds.setRange(0, 3600)
        self.timeout_seconds.setDecimals(1)
        self.timeout_seconds.setSingleStep(0.5)
        self.timeout_seconds.setSuffix(" s")
        layout.addWidget(self.match_mode, 0)
        layout.addWidget(self.expected_text, 1)
        layout.addWidget(self.timeout_seconds, 0)

    def set_condition(
        self,
        *,
        match_mode: str,
        expected_text: str | None,
        timeout_seconds: float | None,
    ) -> None:
        """设置条件字段。"""

        index = self.match_mode.findData(match_mode)
        self.match_mode.setCurrentIndex(max(0, index))
        self.expected_text.setText(expected_text or "")
        self.timeout_seconds.setValue(float(timeout_seconds or 0))

    def condition(self) -> dict[str, object]:
        """返回条件字段。"""

        return {
            "match_mode": self.match_mode.currentData() or "none",
            "expected_text": self.expected_text.text().strip() or None,
            "timeout_seconds": self.timeout_seconds.value() or None,
        }
