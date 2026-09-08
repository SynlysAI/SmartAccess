"""工作流 OCR 条件编辑器。"""

from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QLabel, QLineEdit, QSizePolicy, QWidget

from smartaccess.desktop.widgets.table_style import (
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    set_embedded_editor_height,
)
from smartaccess.shared.contracts.workflow import (
    DEFAULT_OCR_POLL_INTERVAL_SECONDS,
    DEFAULT_OCR_TIMEOUT_SECONDS,
)


class ConditionEditor(QWidget):
    """编辑工作流步骤 OCR 期望条件。"""

    def __init__(self, parent=None) -> None:
        """初始化条件编辑器。"""

        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(58)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)
        self.match_mode = NoWheelComboBox()
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
        self.timeout_seconds = NoWheelDoubleSpinBox()
        self.timeout_seconds.setObjectName("ConditionTimeout")
        set_embedded_editor_height(self.timeout_seconds)
        self.timeout_seconds.setRange(0, 3600)
        self.timeout_seconds.setDecimals(1)
        self.timeout_seconds.setSingleStep(0.5)
        self.timeout_seconds.setSuffix(" s")
        self.timeout_seconds.setMaximumWidth(90)
        self.poll_interval_seconds = NoWheelDoubleSpinBox()
        self.poll_interval_seconds.setObjectName("ConditionPollInterval")
        set_embedded_editor_height(self.poll_interval_seconds)
        self.poll_interval_seconds.setRange(0.1, 60)
        self.poll_interval_seconds.setDecimals(1)
        self.poll_interval_seconds.setSingleStep(0.1)
        self.poll_interval_seconds.setSuffix(" s")
        self.poll_interval_seconds.setMaximumWidth(90)
        for column, title in enumerate(
            ("匹配方式", "期望文字", "识别超时", "轮询间隔")
        ):
            label = QLabel(title)
            label.setObjectName("FieldLabel")
            layout.addWidget(label, 0, column)
        layout.addWidget(self.match_mode, 1, 0)
        layout.addWidget(self.expected_text, 1, 1)
        layout.addWidget(self.timeout_seconds, 1, 2)
        layout.addWidget(self.poll_interval_seconds, 1, 3)
        layout.setColumnStretch(1, 1)

    def set_condition(
        self,
        *,
        match_mode: str,
        expected_text: str | list[str] | None,
        timeout_seconds: float | None,
        poll_interval_seconds: float | None,
        min_confidence: float | None = None,
        ignore_case: bool = False,
        normalize_text: bool = False,
    ) -> None:
        """设置条件字段。"""

        index = self.match_mode.findData(match_mode)
        self.match_mode.setCurrentIndex(max(0, index))
        if isinstance(expected_text, list):
            self.expected_text.setText(" | ".join(str(item) for item in expected_text))
        else:
            self.expected_text.setText(expected_text or "")
        self.timeout_seconds.setValue(
            float(
                timeout_seconds
                if timeout_seconds is not None
                else DEFAULT_OCR_TIMEOUT_SECONDS
            )
        )
        self.poll_interval_seconds.setValue(
            float(
                poll_interval_seconds
                if poll_interval_seconds is not None
                else DEFAULT_OCR_POLL_INTERVAL_SECONDS
            )
        )

    def condition(self) -> dict[str, object]:
        """返回条件字段。"""

        expected_text = self.expected_text.text().strip() or None
        candidates = None
        if expected_text and "|" in expected_text:
            candidates = [
                item.strip()
                for item in expected_text.split("|")
                if item.strip()
            ]
            expected_text = None
        return {
            "match_mode": self.match_mode.currentData() or "none",
            "expected_text": expected_text,
            "expected_candidates": candidates,
            "timeout_seconds": self.timeout_seconds.value() or None,
            "poll_interval_seconds": self.poll_interval_seconds.value(),
            "min_confidence": None,
            "ignore_case": True,
            "normalize_text": True,
        }
