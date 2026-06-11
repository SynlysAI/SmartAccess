"""Read-only UI projections shared by workflow design and overview pages."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from urllib.parse import quote

from smartaccess.desktop.shell import theme as t
from smartaccess.runtime.application.workflow_service import StandardizationResult
from smartaccess.runtime.application.workflow_service import WorkflowDraftRecord
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.workflow import WorkflowContract

REFERENCE_CATEGORY_ORDER = ("observation", "action", "safety", "confirm")
REFERENCE_CATEGORY_LABELS = {
    "observation": "观测",
    "action": "动作",
    "safety": "安全",
    "confirm": "确认",
}
_REFERENCE_SECTION_TITLES = {
    "observation": "观测锚点",
    "action": "动作锚点",
    "safety": "安全确认项",
    "confirm": "人工确认目标",
}


@dataclass(frozen=True, slots=True)
class ContextAnchorView:
    id: str
    type: str
    vision_mode: str
    can_observe: bool
    requires_confirmation: bool

    @property
    def role_label(self) -> str:
        return "观测锚点" if self.can_observe else "动作锚点"

    @property
    def category(self) -> str:
        return "observation" if self.can_observe else "action"

    @property
    def token(self) -> str:
        return f"@{self.id}"

    def to_plain_text(self) -> str:
        confirm = "是" if self.requires_confirmation else "否"
        return f"{self.id} · {self.type} / {self.vision_mode} · 需确认: {confirm}"


@dataclass(frozen=True, slots=True)
class SafetyFieldView:
    field_id: str
    label: str
    risk_level: str
    requires_confirmation: bool

    @property
    def token(self) -> str:
        return f"@field:{self.field_id}"

    def to_plain_text(self) -> str:
        confirm = "是" if self.requires_confirmation else "否"
        return f"{self.label} ({self.field_id}) · 风险: {self.risk_level} · 需确认: {confirm}"


@dataclass(frozen=True, slots=True)
class ContextReferenceView:
    token: str
    category: str
    ref_id: str
    title: str
    subtitle: str
    note: str = ""

    def to_markdown(self, active_tokens: set[str] | None = None) -> str:
        active = " · [已引用]" if active_tokens and self.token in active_tokens else ""
        suffix = f" · {self.note}" if self.note else ""
        return f"`{self.token}` · {self.title} · {self.subtitle}{suffix}{active}"

    def to_plain_text(self) -> str:
        suffix = f" · {self.note}" if self.note else ""
        return f"{self.token} · {self.title} · {self.subtitle}{suffix}"

    def to_html(self, *, active: bool, interactive: bool) -> str:
        border = t.PRIMARY if active else t.HAIRLINE_STRONG
        background = t.PRIMARY_SOFT if active else t.SURFACE_2
        title_color = t.INK if active else t.INK_MUTED
        tags: list[str] = []
        if self.note:
            tags.append(
                f"<span style='color:{t.WARNING if '确认' in self.note else t.INK_SUBTLE};'>"
                f"{html.escape(self.note)}</span>"
            )
        if active:
            tags.append(
                f"<span style='color:{t.PRIMARY_HOVER};font-weight:600;'>已引用</span>"
            )
        token_style = (
            f"display:inline-block;padding:3px 8px;border-radius:999px;"
            f"background:{t.SURFACE_4};color:{t.PRIMARY_HOVER};font-weight:700;"
        )
        token_html = f"<span style='{token_style}'>{html.escape(self.token)}</span>"
        if interactive:
            token_html = (
                f"<a href='insert:{quote(self.token, safe='')}' "
                "style='text-decoration:none;'>"
                f"{token_html}</a>"
            )
        extra_html = ""
        if tags:
            extra_html = (
                f"<div style='margin-top:5px;font-size:12px;'>{' · '.join(tags)}</div>"
            )
        return (
            f"<div style='margin:8px 0;padding:10px 12px;border-radius:10px;"
            f"border:1px solid {border};background:{background};'>"
            f"<div style='margin-bottom:6px;'>{token_html}</div>"
            f"<div style='color:{title_color};font-weight:700;margin-bottom:3px;'>"
            f"{html.escape(self.title)}</div>"
            f"<div style='color:{t.INK_SUBTLE};font-size:12px;line-height:160%;'>"
            f"{html.escape(self.subtitle)}</div>"
            f"{extra_html}"
            "</div>"
        )


@dataclass(frozen=True, slots=True)
class WorkflowContextSnapshot:
    anchor_profile: str
    title_contains: str
    actions: list[str] = field(default_factory=list)
    action_anchors: list[ContextAnchorView] = field(default_factory=list)
    observation_anchors: list[ContextAnchorView] = field(default_factory=list)
    safety_fields: list[SafetyFieldView] = field(default_factory=list)
    manual_confirm_targets: list[str] = field(default_factory=list)
    references: list[ContextReferenceView] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.anchor_profile

    def reference_tokens(self) -> set[str]:
        return {item.token for item in self.references}

    def reference_map(self) -> dict[str, ContextReferenceView]:
        return {item.token: item for item in self.references}

    def categories(self) -> list[str]:
        present = {item.category for item in self.references}
        return [category for category in REFERENCE_CATEGORY_ORDER if category in present]

    def has_category(self, category: str) -> bool:
        return any(item.category == category for item in self.references)

    def items_for_category(self, category: str) -> list[ContextReferenceView]:
        return [item for item in self.references if item.category == category]

    def structured_prompt_references(self, tokens: list[str]) -> list[dict[str, str]]:
        refs = self.reference_map()
        rows: list[dict[str, str]] = []
        for token in tokens:
            item = refs.get(token)
            if item is None:
                continue
            rows.append(
                {
                    "token": item.token,
                    "category": item.category,
                    "ref_id": item.ref_id,
                }
            )
        return rows

    def to_markdown(
        self,
        heading: str = "本次生成读取的上下文快照",
        *,
        active_tokens: set[str] | None = None,
    ) -> str:
        if self.is_empty:
            return f"## {heading}\n\n- 未选择或未找到已校准 anchor_profile。"
        lines = [
            f"## {heading}",
            "",
            f"- anchor_profile：`{self.anchor_profile}`",
            f"- 窗口标题匹配：`{self.title_contains or '未配置'}`",
            f"- 支持动作：{', '.join(f'`{a}`' for a in self.actions) if self.actions else '未声明'}",
        ]
        for category in REFERENCE_CATEGORY_ORDER:
            lines.extend(["", f"### {_REFERENCE_SECTION_TITLES[category]}"])
            items = self.items_for_category(category)
            if items:
                lines.extend(f"- {item.to_markdown(active_tokens)}" for item in items)
            else:
                lines.append("- 无")
        return "\n".join(lines)

    def to_html(
        self,
        *,
        active_tokens: set[str] | None = None,
        interactive: bool = False,
    ) -> str:
        if self.is_empty:
            return "<span>未选择或未找到已校准 anchor_profile。</span>"
        sections = [self._summary_html()]
        active_tokens = active_tokens or set()
        for category in REFERENCE_CATEGORY_ORDER:
            sections.append(
                self._section_html(
                    _REFERENCE_SECTION_TITLES[category],
                    self.items_for_category(category),
                    active_tokens=active_tokens,
                    interactive=interactive,
                )
            )
        return "".join(sections)

    def to_reference_panel_html(
        self,
        category: str,
        *,
        active_tokens: set[str] | None = None,
        interactive: bool = True,
    ) -> str:
        if self.is_empty:
            return "<span>未选择 anchor_profile，无法生成引用。</span>"
        items = self.items_for_category(category)
        if not items:
            return (
                f"<span style='color:{t.INK_SUBTLE};'>"
                f"当前设备暂无“{html.escape(REFERENCE_CATEGORY_LABELS.get(category, category))}”引用项。"
                "</span>"
            )
        rows = [
            f"<div style='color:{t.INK_SUBTLE};margin-bottom:8px;line-height:160%;'>"
            "点击任一 token 即可插入到 Prompt 光标处。"
            "</div>"
        ]
        active_tokens = active_tokens or set()
        rows.extend(
            item.to_html(active=item.token in active_tokens, interactive=interactive)
            for item in items
        )
        return "".join(rows)

    def _summary_html(self) -> str:
        actions = ", ".join(self.actions) if self.actions else "未声明"
        return (
            "<div style='margin-bottom:12px;padding:10px 12px;border-radius:10px;"
            f"border:1px solid {t.HAIRLINE};background:{t.SURFACE_2};line-height:170%;'>"
            f"<div><b>anchor_profile</b>: {html.escape(self.anchor_profile)}</div>"
            f"<div><b>窗口标题匹配</b>: {html.escape(self.title_contains or '未配置')}</div>"
            f"<div><b>支持动作</b>: {html.escape(actions)}</div>"
            "</div>"
        )

    @staticmethod
    def _section_html(
        title: str,
        items: list[ContextReferenceView],
        *,
        active_tokens: set[str],
        interactive: bool,
    ) -> str:
        if not items:
            body = f"<div style='color:{t.INK_SUBTLE};margin-top:6px;'>无</div>"
        else:
            body = "".join(
                item.to_html(active=item.token in active_tokens, interactive=interactive)
                for item in items
            )
        return (
            f"<div style='margin:12px 0 0 0;'>"
            f"<div style='color:{t.INK};font-weight:700;margin-bottom:4px;'>{html.escape(title)}</div>"
            f"{body}</div>"
        )


@dataclass(frozen=True, slots=True)
class WorkflowOverviewProjection:
    workflow_id: str
    anchor_profile: str
    lifecycle_state: str
    prompt: str
    reasoning_markdown: str
    context_snapshot: WorkflowContextSnapshot
    steps: list[dict[str, str]]
    roi_bindings: list[tuple[str, str]]
    outputs: list[tuple[str, str]]
    standardization_ok: bool
    standardization_issues: list[str]


def build_context_snapshot(
    profile: AnchorsContract | None,
) -> WorkflowContextSnapshot:
    if profile is None:
        return WorkflowContextSnapshot(anchor_profile="", title_contains="")
    anchors: list[ContextAnchorView] = []
    for anchor in profile.anchors:
        requires_confirmation = any(
            binding.requires_confirmation for binding in anchor.action_bindings
        )
        anchors.append(
            ContextAnchorView(
                id=anchor.id,
                type=anchor.type or "action_target",
                vision_mode=anchor.vision_mode or "none",
                can_observe=anchor.observe_region is not None,
                requires_confirmation=requires_confirmation,
            )
        )
    action_anchors = sorted(
        [anchor for anchor in anchors if anchor.category == "action"],
        key=lambda item: item.id,
    )
    observation_anchors = sorted(
        [anchor for anchor in anchors if anchor.category == "observation"],
        key=lambda item: item.id,
    )
    safety_fields = [
        SafetyFieldView(
            field_id=field.field_id,
            label=field.label,
            risk_level=field.risk_level,
            requires_confirmation=field.requires_confirmation,
        )
        for field in profile.safety_limits.fields
    ]
    references: list[ContextReferenceView] = []
    for anchor in observation_anchors:
        references.append(
            ContextReferenceView(
                token=anchor.token,
                category=anchor.category,
                ref_id=anchor.id,
                title=anchor.id,
                subtitle=f"{anchor.role_label} · {anchor.type} / {anchor.vision_mode}",
                note="需人工确认" if anchor.requires_confirmation else "",
            )
        )
    for anchor in action_anchors:
        references.append(
            ContextReferenceView(
                token=anchor.token,
                category=anchor.category,
                ref_id=anchor.id,
                title=anchor.id,
                subtitle=f"{anchor.role_label} · {anchor.type} / {anchor.vision_mode}",
                note="需人工确认" if anchor.requires_confirmation else "",
            )
        )
    for field in safety_fields:
        references.append(
            ContextReferenceView(
                token=field.token,
                category="safety",
                ref_id=field.field_id,
                title=field.label,
                subtitle=f"安全字段 · {field.field_id} · 风险 {field.risk_level}",
                note="需人工确认" if field.requires_confirmation else "",
            )
        )
    for anchor_id in sorted(profile.safety_limits.requires_manual_confirm_for):
        references.append(
            ContextReferenceView(
                token=f"@confirm:{anchor_id}",
                category="confirm",
                ref_id=anchor_id,
                title=anchor_id,
                subtitle="人工确认锚点 · 危险动作执行前需确认",
            )
        )
    return WorkflowContextSnapshot(
        anchor_profile=profile.profile_id,
        title_contains=profile.window_signature.title_contains or "",
        actions=list(profile.actions),
        action_anchors=action_anchors,
        observation_anchors=observation_anchors,
        safety_fields=safety_fields,
        manual_confirm_targets=sorted(profile.safety_limits.requires_manual_confirm_for),
        references=references,
    )


def build_workflow_overview_projection(
    workflow: WorkflowContract,
    profile: AnchorsContract | None,
    draft_record: WorkflowDraftRecord | None,
    standardization: StandardizationResult,
) -> WorkflowOverviewProjection:
    prompt = draft_record.prompt if draft_record is not None else "未记录原始 Prompt。"
    reasoning = (
        draft_record.reasoning
        if draft_record is not None and draft_record.reasoning
        else "_尚无本工作流的 AI 推理记录。_"
    )
    steps = [
        {
            "id": step.id,
            "action": step.action,
            "anchor_id": step.anchor_id or "",
            "value": "" if step.value is None else str(step.value),
        }
        for step in workflow.steps
    ]
    return WorkflowOverviewProjection(
        workflow_id=workflow.metadata.workflow_id,
        anchor_profile=workflow.metadata.anchor_profile,
        lifecycle_state=workflow.metadata.lifecycle_state,
        prompt=prompt,
        reasoning_markdown=reasoning,
        context_snapshot=build_context_snapshot(profile),
        steps=steps,
        roi_bindings=sorted(workflow.roi_bindings.items()),
        outputs=[(output.key, output.source) for output in workflow.outputs],
        standardization_ok=standardization.ok,
        standardization_issues=list(standardization.issues),
    )
