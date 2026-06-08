"""The right-hand context panel: details, AI assistant, risk, audit."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QVBoxLayout, QWidget

from .cards import section_title


class _Tab(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(section_title(title))
        self._body = QLabel("—")
        self._body.setWordWrap(True)
        self._body.setStyleSheet("color: #4b5563; line-height: 150%;")
        layout.addWidget(self._body)
        layout.addStretch(1)

    def set_text(self, text: str) -> None:
        self._body.setText(text or "—")


class RightContextPanel(QFrame):
    """Live context inspector shared by every page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanel")
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self._tabs = QTabWidget()
        self.details = _Tab("上下文详情")
        self.assistant = _Tab("AI 助手")
        self.risk = _Tab("风险提示")
        self.audit = _Tab("审计摘要")
        self._tabs.addTab(self.details, "上下文")
        self._tabs.addTab(self.assistant, "AI")
        self._tabs.addTab(self.risk, "风险")
        self._tabs.addTab(self.audit, "审计")
        layout.addWidget(self._tabs, 1)

    def show_context(
        self,
        *,
        details: str = "",
        assistant: str = "",
        risk: str = "",
        audit: str = "",
    ) -> None:
        self.details.set_text(details)
        self.assistant.set_text(assistant)
        self.risk.set_text(risk)
        self.audit.set_text(audit)
