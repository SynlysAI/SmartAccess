"""AI workflow prompt and runtime confirmation widgets."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class AiPromptDialog(QDialog):
    """Reusable wrapped text prompt dialog for AI generation."""

    def __init__(
        self,
        *,
        title: str,
        label: str,
        ai_label: str,
        initial_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        prompt_label = QLabel(f"{label}\n当前 AI：{ai_label}")
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)

        self._editor = QPlainTextEdit()
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.setPlainText(initial_text)
        self._editor.setMinimumHeight(210)
        layout.addWidget(self._editor, 1)

        self._busy_label = QLabel("AI生成中")
        self._busy_label.setObjectName("AiBusyLabel")
        self._busy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._busy_label.setVisible(False)
        layout.addWidget(self._busy_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._ok.setText("生成")
        self._cancel.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text_value(self) -> str:
        """Return the prompt text."""

        return self._editor.toPlainText()

    def set_busy(self, busy: bool, text: str = "AI生成中") -> None:
        """Toggle visible AI generation state."""

        self._busy_label.setText(text)
        self._busy_label.setVisible(busy)
        self._ok.setEnabled(not busy)
        self._cancel.setEnabled(not busy)
        self._editor.setEnabled(not busy)


class AiBusyOverlay(QWidget):
    """Compact prominent status strip for in-page AI generation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AiBusyOverlay")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel("AI生成中")
        self._label.setObjectName("AiBusyOverlayLabel")
        row.addWidget(self._label)
        self.setVisible(False)

    def set_busy(self, busy: bool, text: str = "AI生成中") -> None:
        """Show or hide the strip."""

        self._label.setText(text)
        self.setVisible(busy)
