"""The right-hand toolbar inspector."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtWidgets import QComboBox, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from smartaccess.desktop.shell import theme as t
from smartaccess.runtime.application.workspace_settings import (
    FIXED_DEVICE_ONBOARDING_AI_PROFILE,
    AI_PROFILE_WORKFLOW,
)

from .cards import CollapsibleSection, render_lines_html, rich_text


class _Section(CollapsibleSection):
    """A collapsible section whose body is a single rich-text label."""

    def __init__(self, title: str, *, accent: str, expanded: bool = True) -> None:
        super().__init__(title, accent=accent, expanded=expanded)
        self._body = rich_text(QLabel("-"))
        self._body.setStyleSheet("color:%s;" % t.INK_MUTED)
        self.add(self._body)

    def set_lines(self, lines: Iterable[str]) -> None:
        self._body.setText(render_lines_html(list(lines)))

    def set_text(self, text: str) -> None:
        self._body.setText(render_lines_html([text]))


class _AIConfigSection(CollapsibleSection):
    """Central AI profile selector for workspace-scoped preferences."""

    def __init__(self, *, accent: str, expanded: bool = True) -> None:
        super().__init__("AI 助手", accent=accent, expanded=expanded)
        self._facade = None
        self._syncing = False

        self.add(rich_text(QLabel("设备接入模型选择")))
        self._device_ai_profile = QComboBox()
        self._device_ai_profile.setEnabled(False)
        self._device_ai_profile.setToolTip("设备接入固定使用 Codex，不支持切换。")
        self.add(self._device_ai_profile)

        self.add(rich_text(QLabel("配置工作流模型")))
        self._workflow_ai_profile = QComboBox()
        self.add(self._workflow_ai_profile)

        self._body = rich_text(QLabel("-"))
        self._body.setStyleSheet("color:%s;" % t.INK_MUTED)
        self.add(self._body)

        self._workflow_ai_profile.currentIndexChanged.connect(
            lambda _index: self._save_preference(
                AI_PROFILE_WORKFLOW, self._workflow_ai_profile.currentData()
            )
        )

    def bind_facade(self, facade) -> None:
        self._facade = facade
        self.refresh_options()

    def refresh_options(self) -> None:
        if self._facade is None:
            return
        options = self._facade.ai_model_options()
        profiles = list(options.get("profiles") or [])
        workflow_profile = self._facade.ai_profile_for_purpose(AI_PROFILE_WORKFLOW)

        self._syncing = True
        try:
            self._fill_fixed_device_combo(self._device_ai_profile, profiles)
            self._fill_combo(self._workflow_ai_profile, profiles, workflow_profile)
        finally:
            self._syncing = False

    def set_lines(self, lines: Iterable[str]) -> None:
        self._body.setText(render_lines_html(list(lines)))

    def _save_preference(self, purpose: str, profile_id: str | None) -> None:
        if self._syncing or self._facade is None:
            return
        setter = getattr(self._facade, "set_ai_profile_preference", None)
        if callable(setter):
            setter(purpose, str(profile_id or ""))

    @staticmethod
    def _fill_combo(combo: QComboBox, profiles: list[dict], selected_profile: str) -> None:
        combo.clear()
        if not profiles:
            combo.addItem("Manual / current default", "")
            return
        for profile in profiles:
            label = str(profile.get("label") or profile.get("profile_id") or "")
            model = str(profile.get("model") or "")
            configured = "ready" if profile.get("configured") else "missing key"
            combo.addItem(f"{label} / {model} ({configured})", profile.get("profile_id"))
        selected_index = combo.findData(selected_profile)
        combo.setCurrentIndex(max(0, selected_index))

    @staticmethod
    def _fill_fixed_device_combo(combo: QComboBox, profiles: list[dict]) -> None:
        combo.clear()
        profile = next(
            (
                item
                for item in profiles
                if str(item.get("profile_id") or "") == FIXED_DEVICE_ONBOARDING_AI_PROFILE
            ),
            None,
        )
        if profile is None:
            combo.addItem("Codex / unavailable (missing profile)", FIXED_DEVICE_ONBOARDING_AI_PROFILE)
            return
        label = str(profile.get("label") or profile.get("profile_id") or "Codex")
        model = str(profile.get("model") or "")
        configured = "ready" if profile.get("configured") else "missing key"
        combo.addItem(f"{label} / {model} ({configured})", profile.get("profile_id"))


class RightContextPanel(QFrame):
    """Live context inspector shared by every page."""

    def __init__(self, facade=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.details = _Section("工具详情", accent=t.PRIMARY)
        self.assistant = _AIConfigSection(accent="#a5b4fc")
        self.risk = _Section("风险提示", accent=t.WARNING)
        self.audit = _Section("审计摘要", accent=t.SUCCESS, expanded=False)
        for section in (self.details, self.assistant, self.risk, self.audit):
            layout.addWidget(section)
        layout.addStretch(1)

        scroll.setWidget(host)
        outer.addWidget(scroll)
        if facade is not None:
            self.bind_facade(facade)

    @property
    def _workflow_ai_profile(self) -> QComboBox:
        return self.assistant._workflow_ai_profile

    @property
    def _device_ai_profile(self) -> QComboBox:
        return self.assistant._device_ai_profile

    def bind_facade(self, facade) -> None:
        self.assistant.bind_facade(facade)

    def show_context(
        self,
        *,
        details: Iterable[str] | str = "",
        assistant: Iterable[str] | str = "",
        risk: Iterable[str] | str = "",
        audit: Iterable[str] | str = "",
    ) -> None:
        self.details.set_lines(_as_lines(details))
        self.assistant.refresh_options()
        self.assistant.set_lines(_as_lines(assistant))
        self.risk.set_lines(_as_lines(risk))
        self.audit.set_lines(_as_lines(audit))


def _as_lines(value: Iterable[str] | str) -> list[str]:
    if isinstance(value, str):
        return [ln for ln in value.split("\n") if ln.strip()]
    return list(value)
