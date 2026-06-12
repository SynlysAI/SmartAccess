"""Workflow design page: AI draft, evidence trace, and editable steps."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t
from smartaccess.desktop.viewmodels.workflow_vm import WorkflowViewModel
from smartaccess.desktop.widgets.cards import (
    Card,
    CollapsibleSection,
    hint_label,
    page_header,
    rich_text,
    section_title,
)
from smartaccess.desktop.workflow_projection import WorkflowContextSnapshot, build_context_snapshot
from smartaccess.runtime.application.workspace_settings import AI_PROFILE_WORKFLOW
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)

_ACTION_NOTES = {
    "click": "单击控件",
    "type": "输入文本",
    "press_enter": "按回车键",
    "hotkey": "发送快捷键",
}
_OBSERVATION_TYPES = {"observation", "readout", "status", "region", "roi"}
_MOVE_UP_GLYPH = "↑"
_MOVE_DOWN_GLYPH = "↓"
_DELETE_GLYPH = "×"
_TAB_NAME_TO_INDEX = {"steps": 0}
_STEP_CONDITION_ROLE = Qt.ItemDataRole.UserRole + 10
_STEP_TABLE_BASE_ROW_HEIGHT = 52
_STEP_TABLE_MAX_VISIBLE_ROWS = 9


def _metadata_with_anchor_profile(
    metadata: WorkflowMetadata, anchor_profile: str
) -> WorkflowMetadata:
    payload = metadata.model_dump(mode="json", exclude_none=True)
    payload["anchor_profile"] = anchor_profile
    return WorkflowMetadata.model_validate(payload)


class WorkflowPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = WorkflowViewModel(facade, self)
        self._current: WorkflowContract | None = None
        self._loading = False
        self._context_snapshot = build_context_snapshot(None)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        header_row = QHBoxLayout()
        header_row.addWidget(
            page_header("工作流设计", "通过设备信息生成、审阅并标准化可执行工作流。"),
            1,
        )
        self._draft_panel_toggle = QPushButton("AI 助手")
        self._draft_panel_toggle.setObjectName("Ghost")
        self._draft_panel_toggle.setCheckable(True)
        self._draft_panel_toggle.setChecked(False)
        self._draft_panel_toggle.setToolTip("显示或隐藏左侧 AI 助手面板。")
        header_row.addWidget(self._draft_panel_toggle)
        self._review_panel_toggle = QPushButton("审阅面板")
        self._review_panel_toggle.setObjectName("Ghost")
        self._review_panel_toggle.setCheckable(True)
        self._review_panel_toggle.setChecked(False)
        self._review_panel_toggle.setToolTip("显示或隐藏右侧审阅面板。")
        header_row.addWidget(self._review_panel_toggle)
        root.addLayout(header_row)

        self._inner = QMainWindow()
        self._inner.setDockOptions(QMainWindow.DockOption.AnimatedDocks)
        self._inner.setCentralWidget(self._build_right())

        self._draft_dock = QDockWidget("AI 助手", self._inner)
        self._draft_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._draft_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._draft_dock.setWidget(self._build_left())
        self._inner.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._draft_dock)

        self._review_dock = QDockWidget("审阅面板", self._inner)
        self._review_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._review_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._review_dock.setWidget(self._build_review_panel())
        self._inner.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._review_dock)
        self._draft_dock.hide()
        self._review_dock.hide()
        root.addWidget(self._inner, 1)

        self._draft_panel_toggle.toggled.connect(self._draft_dock.setVisible)
        self._draft_dock.visibilityChanged.connect(self._draft_panel_toggle.setChecked)
        self._review_panel_toggle.toggled.connect(self._review_dock.setVisible)
        self._review_dock.visibilityChanged.connect(self._review_panel_toggle.setChecked)

        self._reload()
        self._set_prompt_text("")

    def on_show(self) -> None:
        self._reload()
        if self._current is not None:
            self._refresh_context_panel()
            self._refresh_reasoning_view()
        self._fit_steps_table_to_content()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_steps_table"):
            self._fit_steps_table_to_content()

    def focus_workflow(self, workflow_id: str, *, section: str | None = None) -> None:
        workflows = self._vm.list_workflows()
        for row, workflow in enumerate(workflows):
            if workflow.metadata.workflow_id == workflow_id:
                self._workflows.setCurrentRow(row)
                self._show_workflow(workflow)
                break
        if section is not None:
            idx = _TAB_NAME_TO_INDEX.get(section)
            if idx is not None:
                self._editor_tabs.setCurrentIndex(idx)

    def current_workflow_id(self) -> str:
        return self._current.metadata.workflow_id if self._current else ""

    # ------------------------------------------------------------------ #
    def _build_left(self) -> QWidget:
        left = Card()
        left.setMinimumWidth(420)
        left.add(section_title("AI 助手"))
        left.add(self._build_draft_mode())
        return left

    def _build_draft_mode(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        self._gen_label = hint_label("")
        layout.addWidget(self._gen_label)

        meta = QWidget()
        meta_row = QHBoxLayout(meta)
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(10)

        workflow_box = QWidget()
        workflow_layout = QVBoxLayout(workflow_box)
        workflow_layout.setContentsMargins(0, 0, 0, 0)
        workflow_layout.setSpacing(6)
        self._workflow_id_label = QLabel("工作流 ID")
        self._workflow_id_label.setObjectName("Body")
        self._workflow_id = QLineEdit("wf_new_experiment")
        self._workflow_id.setPlaceholderText("例如 wf_new_experiment")
        workflow_layout.addWidget(self._workflow_id_label)
        workflow_layout.addWidget(self._workflow_id)

        anchor_profile_box = QWidget()
        anchor_profile_layout = QVBoxLayout(anchor_profile_box)
        anchor_profile_layout.setContentsMargins(0, 0, 0, 0)
        anchor_profile_layout.setSpacing(6)
        self._anchor_profile_label = QLabel("anchor_profile")
        self._anchor_profile_label.setObjectName("Body")
        self._anchor_profile = QComboBox()
        self._anchor_profile.currentIndexChanged.connect(self._on_anchor_profile_changed)
        anchor_profile_layout.addWidget(self._anchor_profile_label)
        anchor_profile_layout.addWidget(self._anchor_profile)

        meta_row.addWidget(workflow_box, 1)
        meta_row.addWidget(anchor_profile_box, 1)
        layout.addWidget(meta)

        self._prompt_label = QLabel("自动化目标")
        self._prompt_label.setObjectName("Body")
        layout.addWidget(self._prompt_label)
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("用自然语言描述要完成的实验或操作流程。AI 会自动结合 Memory、Skill 和当前锚点集生成步骤。")
        self._prompt.setMaximumHeight(150)
        layout.addWidget(self._prompt)

        generate = QPushButton("生成工作流")
        generate.clicked.connect(self._generate)
        layout.addWidget(generate)

        layout.addWidget(section_title("生成依据与编排过程"))
        self._reasoning = QTextBrowser()
        self._reasoning.setObjectName("LogView")
        self._reasoning.setOpenExternalLinks(False)
        self._reasoning.setMinimumHeight(280)
        layout.addWidget(self._reasoning, 1)
        return page

    def _build_review_mode(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        self._workflows_section = CollapsibleSection("已有工作流", expanded=True)
        self._workflows = QListWidget()
        self._workflows.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._workflows.customContextMenuRequested.connect(self._on_workflows_context_menu)
        self._workflows.itemSelectionChanged.connect(self._select_existing)
        self._workflows_section.add(self._workflows)
        layout.addWidget(self._workflows_section, 1)
        return page

    def _build_review_panel(self) -> QWidget:
        review = Card()
        review.setMinimumWidth(360)
        review.add(section_title("工作流列表"))
        review.add(self._build_review_mode())
        return review

    def _build_right(self) -> QWidget:
        right = Card(flush=True)

        self._editor_tabs = QTabWidget()

        steps_page = QWidget()
        steps_layout = QVBoxLayout(steps_page)
        steps_layout.setContentsMargins(12, 12, 12, 12)
        steps_layout.setSpacing(8)
        steps_layout.addWidget(
            hint_label("生成的步骤可在此手动修改、调整顺序或删除。确认无误后保存工作流。")
        )
        self._steps_table = QTableWidget(0, 7)
        self._steps_table.setHorizontalHeaderLabels(["步骤 ID", "动作", "anchor_id", "值", "条件", "上移/下移", ""])
        self._steps_table.setWordWrap(False)
        self._steps_table.verticalHeader().setDefaultSectionSize(_STEP_TABLE_BASE_ROW_HEIGHT)
        self._steps_table.verticalHeader().setMinimumSectionSize(_STEP_TABLE_BASE_ROW_HEIGHT)
        steps_header = self._steps_table.horizontalHeader()
        steps_header.setStretchLastSection(False)
        steps_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._steps_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._steps_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._steps_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._steps_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._steps_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._steps_table.itemChanged.connect(lambda _item: self._fit_steps_table_to_content())
        steps_layout.addWidget(self._steps_table, 1)
        step_controls = QWidget()
        step_row = QHBoxLayout(step_controls)
        step_row.setContentsMargins(0, 0, 0, 0)
        add_step = QPushButton("+ 添加步骤")
        add_step.setObjectName("Ghost")
        add_step.clicked.connect(self._add_step_row)
        step_row.addWidget(add_step)
        insert_step = QPushButton("插入步骤")
        insert_step.setObjectName("Ghost")
        insert_step.clicked.connect(self._insert_step_after_selection)
        step_row.addWidget(insert_step)
        step_row.addStretch(1)
        steps_layout.addWidget(step_controls)
        self._editor_tabs.addTab(steps_page, "步骤编排")

        right.add(self._editor_tabs)

        action_controls = QWidget()
        action_row = QHBoxLayout(action_controls)
        action_row.setContentsMargins(12, 8, 12, 4)
        action_row.addStretch(1)
        save = QPushButton("保存工作流配置")
        save.clicked.connect(self._save_workflow)
        action_row.addWidget(save)
        right.add(action_controls)

        self._precheck_section = CollapsibleSection("标准化预检", accent=t.WARNING)
        self._precheck = rich_text(QLabel("尚未运行标准化检查。"))
        check = QPushButton("运行标准化检查")
        check.setObjectName("Ghost")
        check.clicked.connect(self._standardize)
        self._precheck_section.add(self._precheck)
        self._precheck_section.add(check)
        right.add(self._precheck_section)

        return right

    # ------------------------------------------------------------------ #
    def _reload(self) -> None:
        current_anchor_profile = (
            self._anchor_profile.currentText() if hasattr(self, "_anchor_profile") else ""
        )
        self._loading = True
        self._anchor_profile.clear()
        self._anchor_profile.addItems(self._vm.list_anchor_profiles() or ["unknown_device"])
        if current_anchor_profile:
            idx = self._anchor_profile.findText(current_anchor_profile)
            if idx >= 0:
                self._anchor_profile.setCurrentIndex(idx)
        self._loading = False
        self._gen_label.setText(f"当前 AI 助手：{self._vm.generator_label()}")
        selected_id = self._current.metadata.workflow_id if self._current else ""
        self._workflows.clear()
        selected_row = -1
        for row, entry in enumerate(self._vm.list_workflows_projected()):
            item = QListWidgetItem(entry.display_label)
            item.setData(Qt.ItemDataRole.UserRole, entry.workflow.metadata.workflow_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry.source_kind)
            item.setData(Qt.ItemDataRole.UserRole + 2, entry.storage_ref)
            self._workflows.addItem(item)
            if entry.workflow.metadata.workflow_id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self._workflows.setCurrentRow(selected_row)
        self._refresh_context_panel()
        self._refresh_reasoning_view()

    def _generate(self) -> None:
        try:
            workflow = self._vm.generate(
                self._prompt.toPlainText(),
                anchor_profile=self._anchor_profile.currentText() or None,
                workflow_id=self._workflow_id.text().strip() or "wf_new_experiment",
                ai_profile_id=self._workflow_ai_profile_id(),
            )
        except Exception as exc:  # noqa: BLE001
            self._refresh_reasoning_view(error=exc)
            QMessageBox.critical(self, "生成失败", str(exc))
            return
        self._show_workflow(workflow)
        self._reload()

    def _workflow_ai_profile_id(self) -> str:
        return self._vm.ai_profile_for_purpose(AI_PROFILE_WORKFLOW)

    def _select_existing(self) -> None:
        if self._loading:
            return
        item = self._workflows.currentItem()
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        if not workflow_id:
            return
        workflows = self._vm.list_workflows()
        for wf in workflows:
            if wf.metadata.workflow_id == workflow_id:
                self._show_workflow(wf)
                return

    def _on_workflows_context_menu(self, pos) -> None:
        item = self._workflows.itemAt(pos)
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        source_kind = item.data(Qt.ItemDataRole.UserRole + 1) or "draft"
        storage_ref = item.data(Qt.ItemDataRole.UserRole + 2) or ""
        if not workflow_id:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除工作流")
        action = menu.exec(self._workflows.mapToGlobal(pos))
        if action == delete_action:
            self._delete_workflow_item(workflow_id, source_kind, storage_ref)

    def _delete_workflow_item(self, workflow_id: str, source_kind: str, storage_ref: str) -> None:
        """Delete a workflow: draft is local-only; template copy goes cloud-first."""
        if source_kind == "local_template":
            # Parse template_id@template_version from storage_ref
            parts = storage_ref.split("@")
            if len(parts) != 2:
                QMessageBox.warning(self, "删除失败", f"无法解析模板标识: {storage_ref}")
                return
            template_id, template_version = parts
            reply = QMessageBox.question(
                self, "确认删除",
                f"将删除本地模板副本「{workflow_id}」\n"
                f"云端模板 {template_id}@{template_version} 也将被删除。\n\n确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                self._vm.delete_template_cloud_first(template_id, template_version, force=True)
            except Exception as exc:
                QMessageBox.critical(self, "删除失败", str(exc))
                return
        else:
            # Draft: local only
            reply = QMessageBox.question(
                self, "确认删除",
                f"将删除本地草稿「{workflow_id}」。\n此操作不可撤销。\n\n确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                self._vm.delete_workflow(workflow_id)
            except Exception as exc:
                QMessageBox.critical(self, "删除失败", str(exc))
                return
        self._reload()
        QMessageBox.information(self, "已删除", f"工作流 {workflow_id} 已删除。")

    def _show_workflow(self, workflow: WorkflowContract) -> None:
        self._current = workflow
        self._workflow_id.setText(workflow.metadata.workflow_id)
        self._sync_anchor_profile_to_workflow(workflow)
        self._refresh_context_panel()
        self._restore_prompt_for_workflow(workflow)
        self._populate_steps_table(workflow)
        self._refresh_context_panel()
        self._refresh_reasoning_view()
        self._precheck.setText("已加载工作流，可编辑步骤后保存或运行标准化检查。")
        self._fit_steps_table_to_content()

    def _restore_prompt_for_workflow(self, workflow: WorkflowContract) -> None:
        record = self._vm.draft_record(workflow.metadata.workflow_id)
        prompt = record.prompt if record is not None else ""
        self._set_prompt_text(prompt or "")

    def _sync_anchor_profile_to_workflow(self, workflow: WorkflowContract) -> None:
        anchor_profile = workflow.metadata.anchor_profile
        idx = self._anchor_profile.findText(anchor_profile)
        if idx >= 0:
            self._loading = True
            self._anchor_profile.setCurrentIndex(idx)
            self._loading = False

    def _on_anchor_profile_changed(self) -> None:
        if self._loading:
            return
        self._refresh_context_panel()
        self._refresh_reasoning_view()

    def _set_prompt_text(self, text: str) -> None:
        self._prompt.setPlainText(text)

    def _refresh_context_panel(self) -> None:
        profile = self._vm.get_anchor_profile(self._anchor_profile.currentText() or None)
        self._context_snapshot = build_context_snapshot(profile)

    def _refresh_reasoning_view(self, error: Exception | None = None) -> None:
        if self._current is not None:
            record = self._vm.draft_record(self._current.metadata.workflow_id)
            if record is not None:
                anchor_profile = record.context.get("anchor_profile") or None
                profile = self._vm.get_anchor_profile(anchor_profile)
                snapshot = build_context_snapshot(profile)
                self._reasoning.setHtml(self._reasoning_html(snapshot, record.reasoning, record.context))
                return
            self._reasoning.setHtml(self._reasoning_html(self._context_snapshot, "", {}))
            return
        if error is not None:
            self._reasoning.setHtml(self._reasoning_error_html(error))
            return
        self._reasoning.setHtml(
            f"<span style='color:{t.INK_SUBTLE};'>生成工作流后，这里会显示引用锚点、知识命中和编排过程。</span>"
        )

    def _reasoning_html(
        self,
        snapshot: WorkflowContextSnapshot,
        reasoning: str,
        context: dict,
    ) -> str:
        anchors = context.get("anchors") or []
        knowledge_hits = context.get("_knowledge_hits") or []
        workflow = self._current
        rows: list[str] = [
            "<div style='line-height:165%;'>",
            self._evidence_header(snapshot),
            self._evidence_section("知识命中", self._knowledge_hit_cards(knowledge_hits)),
            self._evidence_section("引用锚点", self._anchor_cards(anchors, snapshot)),
        ]
        if workflow is not None:
            rows.append(self._evidence_section("步骤编排", self._step_cards(workflow)))
            rows.append(self._evidence_section("标准化结论", self._check_cards(workflow)))
        if reasoning:
            rows.append(self._evidence_section("生成器摘要", self._plain_reasoning_block(reasoning)))
        rows.append("</div>")
        return "".join(rows)

    def _evidence_header(self, snapshot: WorkflowContextSnapshot) -> str:
        return (
            f"<div style='padding:10px 12px;border:1px solid {t.HAIRLINE_STRONG};"
            f"background:{t.SURFACE_2};border-radius:8px;margin-bottom:10px;'>"
            f"<div style='color:{t.INK};font-weight:700;'>"
            f"{html.escape(snapshot.anchor_profile or '未选择锚点集')}</div>"
            f"<div style='color:{t.INK_SUBTLE};font-size:12px;'>窗口标题："
            f"{html.escape(snapshot.title_contains or '未配置')}</div>"
            f"<div style='margin-top:6px;'>{self._tag('memory', 'Memory', t.WARNING)}"
            f"{self._tag('skill', 'Skill', t.PRIMARY_HOVER)}"
            f"{self._tag('action', '动作锚点', t.SUCCESS)}"
            f"{self._tag('ocr', 'OCR 观测', '#22d3ee')}"
            f"{self._tag('confirm', '需确认', t.DANGER)}</div>"
            "</div>"
        )

    def _knowledge_hit_cards(self, hits: list[dict]) -> str:
        if not hits:
            return (
                f"<div style='color:{t.INK_SUBTLE};'>未命中显式 Memory/Skill，按当前锚点集和内置编排规则生成。</div>"
            )
        cards: list[str] = []
        for hit in hits:
            kind = str(hit.get("kind") or hit.get("type") or "memory").lower()
            color = t.PRIMARY_HOVER if "skill" in kind else t.WARNING
            title = str(hit.get("title") or hit.get("id") or kind)
            summary = str(hit.get("summary") or hit.get("content") or "")
            cards.append(
                self._mini_card(
                    self._tag(kind, "Skill" if "skill" in kind else "Memory", color),
                    title,
                    summary,
                )
            )
        return "".join(cards)

    def _anchor_cards(self, anchors: list[dict], snapshot: WorkflowContextSnapshot) -> str:
        rows: list[str] = []
        if anchors:
            for anchor in anchors:
                anchor_id = str(anchor.get("id") or "")
                can_observe = bool(anchor.get("observe_region"))
                confirm = any(
                    bool(binding.get("requires_confirmation"))
                    for binding in anchor.get("action_bindings") or []
                    if isinstance(binding, dict)
                )
                tags = self._tag("action", "action", t.SUCCESS)
                if can_observe:
                    tags += self._tag("ocr", "ocr", "#22d3ee")
                if confirm:
                    tags += self._tag("confirm", "confirm", t.DANGER)
                actions = ", ".join(str(a) for a in anchor.get("supported_actions") or [])
                rows.append(self._mini_card(tags, anchor_id, f"支持动作：{actions or 'click'}"))
        else:
            for item in snapshot.references:
                color = "#22d3ee" if item.category == "observation" else t.SUCCESS
                rows.append(self._mini_card(self._tag(item.category, item.category, color), item.ref_id, item.subtitle))
        return "".join(rows) if rows else f"<div style='color:{t.INK_SUBTLE};'>当前锚点集暂无可用锚点。</div>"

    def _step_cards(self, workflow: WorkflowContract) -> str:
        if not workflow.steps:
            return f"<div style='color:{t.INK_SUBTLE};'>尚未生成步骤。</div>"
        rows: list[str] = []
        for index, step in enumerate(workflow.steps, 1):
            needs_ocr = bool(step.expected_text) or step.match_mode == "not_empty"
            tags = self._tag("step", f"{index}", t.PRIMARY_HOVER)
            tags += self._tag("action", step.action, t.SUCCESS)
            tags += self._tag("ocr", "OCR 轮询" if needs_ocr else "固定等待", "#22d3ee" if needs_ocr else t.INK_SUBTLE)
            if step.requires_confirmation:
                tags += self._tag("confirm", "需确认", t.DANGER)
            expectation = "无需观测校验"
            if needs_ocr:
                expectation = f"{step.match_mode} · {step.expected_text or '非空文本'} · {step.timeout_seconds or '默认'}s"
            value = f" · value={step.value}" if step.value is not None else ""
            rows.append(self._mini_card(tags, step.id, f"{step.anchor_id} · {expectation}{value}"))
        return "".join(rows)

    def _check_cards(self, workflow: WorkflowContract) -> str:
        result = self._vm.standardize(workflow)
        if result.ok:
            return self._mini_card(self._tag("check", "check", t.SUCCESS), "标准化检查通过", "锚点、动作和 OCR 观测配置一致。")
        return "".join(
            self._mini_card(self._tag("check", "check", t.DANGER), "需要修复", issue)
            for issue in result.issues
        )

    def _plain_reasoning_block(self, reasoning: str) -> str:
        return (
            f"<pre style='white-space:pre-wrap;color:{t.INK_MUTED};"
            f"background:{t.SURFACE_2};border:1px solid {t.HAIRLINE};"
            "border-radius:8px;padding:10px;'>"
            f"{html.escape(reasoning[:2200])}</pre>"
        )

    def _reasoning_error_html(self, error: Exception) -> str:
        return (
            f"<div style='color:{t.DANGER};font-weight:700;margin-bottom:8px;'>生成失败</div>"
            f"<div style='color:{t.INK_MUTED};white-space:pre-wrap;'>{html.escape(str(error))}</div>"
        )

    @staticmethod
    def _tag(kind: str, label: str, color: str) -> str:
        return (
            f"<span style='display:inline-block;margin:2px 5px 2px 0;padding:2px 7px;"
            f"border-radius:6px;border:1px solid {color};color:{color};"
            f"background:{t.SURFACE_1};font-size:11px;font-weight:700;'>"
            f"{html.escape(label)}</span>"
        )

    @staticmethod
    def _mini_card(tags: str, title: str, detail: str) -> str:
        return (
            f"<div style='margin:6px 0;padding:8px 10px;border:1px solid {t.HAIRLINE};"
            f"background:{t.SURFACE_2};border-radius:8px;'>"
            f"<div>{tags}</div>"
            f"<div style='color:{t.INK};font-weight:700;margin-top:3px;'>{html.escape(title)}</div>"
            f"<div style='color:{t.INK_SUBTLE};font-size:12px;margin-top:2px;'>"
            f"{html.escape(detail)}</div></div>"
        )

    @staticmethod
    def _evidence_section(title: str, body: str) -> str:
        return (
            f"<div style='margin:12px 0;'>"
            f"<div style='color:{t.INK};font-weight:700;margin-bottom:5px;'>{html.escape(title)}</div>"
            f"{body}</div>"
        )

    # --- editable steps --------------------------------------------------- #
    def _populate_steps_table(self, workflow: WorkflowContract) -> None:
        self._steps_table.setRowCount(0)
        for step in workflow.steps:
            condition = None
            if step.match_mode != "none":
                condition = {
                    "expected_text": step.expected_text or "",
                    "match_mode": step.match_mode,
                    "timeout_seconds": step.timeout_seconds or 10.0,
                }
            self._insert_step_row(
                step.id,
                step.action,
                step.anchor_id or "",
                step.value or "",
                condition=condition,
            )
        self._fit_steps_table_to_content()

    def _add_step_row(self) -> None:
        step_num = self._steps_table.rowCount() + 1
        self._insert_step_row(f"step_{step_num}", "click", "", "")
        self._renumber_steps()
        self._fit_steps_table_to_content()

    def _insert_step_after_selection(self) -> None:
        selected = self._steps_table.currentRow()
        if selected < 0 or selected >= self._steps_table.rowCount():
            self._add_step_row()
            return
        step_num = self._steps_table.rowCount() + 1
        self._insert_step_at(f"step_{step_num}", "click", "", "", selected + 1)
        self._renumber_steps()
        self._fit_steps_table_to_content()

    def _insert_step_at(
        self,
        step_id: str,
        action: str,
        anchor_id: str,
        value: str,
        row: int,
        *,
        condition: dict | None = None,
    ) -> None:
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, self._make_step_item(step_id))

        action_combo = self._make_action_combo(action)
        self._steps_table.setCellWidget(row, 1, action_combo)

        self._steps_table.setItem(row, 2, self._make_step_item(anchor_id))
        self._steps_table.setItem(row, 3, self._make_step_item(str(value)))
        self._set_row_condition(row, condition)

        self._steps_table.setCellWidget(row, 4, self._make_condition_button(row))

        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setContentsMargins(2, 2, 2, 2)
        move_layout.setSpacing(4)
        up_btn = self._make_icon_button(_MOVE_UP_GLYPH, object_name="Ghost", tooltip="上移步骤")
        up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
        down_btn = self._make_icon_button(_MOVE_DOWN_GLYPH, object_name="Ghost", tooltip="下移步骤")
        down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
        move_layout.addWidget(up_btn)
        move_layout.addWidget(down_btn)
        self._steps_table.setCellWidget(row, 5, move_widget)

        delete = self._make_delete_button("删除步骤")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
        self._steps_table.setCellWidget(row, 6, delete)
        self._rebind_step_buttons()
        self._fit_steps_table_to_content()

    def _insert_step_row(
        self,
        step_id: str,
        action: str,
        anchor_id: str,
        value: str,
        *,
        condition: dict | None = None,
    ) -> None:
        row = self._steps_table.rowCount()
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, self._make_step_item(step_id))

        action_combo = self._make_action_combo(action)
        self._steps_table.setCellWidget(row, 1, action_combo)
        self._steps_table.setItem(row, 2, self._make_step_item(anchor_id))
        self._steps_table.setItem(row, 3, self._make_step_item(str(value)))
        self._set_row_condition(row, condition)

        self._steps_table.setCellWidget(row, 4, self._make_condition_button(row))

        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setContentsMargins(2, 2, 2, 2)
        move_layout.setSpacing(4)
        up_btn = self._make_icon_button(_MOVE_UP_GLYPH, object_name="Ghost", tooltip="上移步骤")
        up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
        down_btn = self._make_icon_button(_MOVE_DOWN_GLYPH, object_name="Ghost", tooltip="下移步骤")
        down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
        move_layout.addWidget(up_btn)
        move_layout.addWidget(down_btn)
        self._steps_table.setCellWidget(row, 5, move_widget)

        delete = self._make_delete_button("删除步骤")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
        self._steps_table.setCellWidget(row, 6, delete)
        self._fit_steps_table_to_content()

    def _delete_step_row(self, row: int) -> None:
        self._steps_table.removeRow(row)
        self._rebind_step_buttons()
        self._renumber_steps()
        self._fit_steps_table_to_content()

    def _move_step_up(self, row: int) -> None:
        if row <= 0:
            return
        self._swap_step_rows(row, row - 1)

    def _move_step_down(self, row: int) -> None:
        if row >= self._steps_table.rowCount() - 1:
            return
        self._swap_step_rows(row, row + 1)

    def _swap_step_rows(self, row1: int, row2: int) -> None:
        data1 = self._collect_step_row_data(row1)
        data2 = self._collect_step_row_data(row2)
        self._set_step_row_data(row1, data2)
        self._set_step_row_data(row2, data1)
        self._renumber_steps()
        self._rebind_step_buttons()
        self._fit_steps_table_to_content()

    def _renumber_steps(self) -> None:
        for row in range(self._steps_table.rowCount()):
            item = self._steps_table.item(row, 0)
            if item is not None:
                step_id = f"step_{row + 1}"
                item.setText(step_id)
                item.setToolTip(step_id)

    def _edit_condition(self, row: int) -> None:
        """Open the condition editor for a step row."""
        from smartaccess.desktop.widgets.condition_editor import ConditionEditorDialog

        current = self._row_condition(row)
        dlg = ConditionEditorDialog(current, parent=self)
        if dlg.exec() == ConditionEditorDialog.DialogCode.Accepted:
            condition = dlg.condition_dict()
            if condition.get("match_mode") == "none":
                self._set_row_condition(row, None)
            else:
                self._set_row_condition(row, condition)
            self._steps_table.setCellWidget(row, 4, self._make_condition_button(row))
            self._fit_steps_table_to_content()

    def _make_condition_button(self, row: int) -> QPushButton:
        summary = self._condition_summary(self._row_condition(row))
        button = QPushButton(summary)
        button.setObjectName("Ghost")
        button.setToolTip(f"{summary}\n编辑 OCR 期望 (expected_text/match_mode/timeout_seconds)")
        button.setMinimumHeight(30)
        button.clicked.connect(lambda _checked=False, r=row: self._edit_condition(r))
        return button

    def _row_condition(self, row: int) -> dict | None:
        item = self._steps_table.item(row, 0)
        condition = item.data(_STEP_CONDITION_ROLE) if item is not None else None
        return dict(condition) if isinstance(condition, dict) else None

    def _set_row_condition(self, row: int, condition: dict | None) -> None:
        item = self._steps_table.item(row, 0)
        if item is not None:
            item.setData(_STEP_CONDITION_ROLE, dict(condition) if condition else None)

    @staticmethod
    def _make_step_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        return item

    @staticmethod
    def _make_action_combo(action: str) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(34)
        for act_key, act_label in _ACTION_NOTES.items():
            combo.addItem(f"{act_key} · {act_label}", act_key)
        idx = combo.findData(action)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)
        return combo

    @staticmethod
    def _condition_summary(condition: dict | None) -> str:
        if not condition:
            return "未配置"
        match_mode = str(condition.get("match_mode") or "none")
        expected = str(condition.get("expected_text") or "")
        timeout = condition.get("timeout_seconds") or ""
        main = f"OCR · {match_mode}"
        if expected:
            main = f"{main} {expected}"
        if timeout:
            main = f"{main} · {timeout}s"
        return main

    def _collect_step_row_data(self, row: int) -> tuple[str, str, str, str, dict | None]:
        step_id = self._table_text(self._steps_table, row, 0)
        action_combo = self._steps_table.cellWidget(row, 1)
        action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
        anchor_id = self._table_text(self._steps_table, row, 2)
        value = self._table_text(self._steps_table, row, 3)
        return (step_id, action, anchor_id, value, self._row_condition(row))

    def _set_step_row_data(self, row: int, data: tuple[str, str, str, str, dict | None]) -> None:
        step_id, action, anchor_id, value, condition = data
        self._steps_table.item(row, 0).setText(step_id)
        action_combo = self._steps_table.cellWidget(row, 1)
        if isinstance(action_combo, QComboBox):
            idx = action_combo.findData(action)
            if idx >= 0:
                action_combo.setCurrentIndex(idx)
        self._steps_table.item(row, 2).setText(anchor_id)
        self._steps_table.item(row, 2).setToolTip(anchor_id)
        self._steps_table.item(row, 3).setText(value)
        self._steps_table.item(row, 3).setToolTip(value)
        self._set_row_condition(row, condition)

    def _rebind_step_buttons(self) -> None:
        for row in range(self._steps_table.rowCount()):
            self._steps_table.setCellWidget(row, 4, self._make_condition_button(row))

            move_widget = QWidget()
            move_layout = QHBoxLayout(move_widget)
            move_layout.setContentsMargins(2, 2, 2, 2)
            move_layout.setSpacing(4)
            up_btn = self._make_icon_button(_MOVE_UP_GLYPH, object_name="Ghost", tooltip="上移步骤")
            up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
            down_btn = self._make_icon_button(_MOVE_DOWN_GLYPH, object_name="Ghost", tooltip="下移步骤")
            down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
            move_layout.addWidget(up_btn)
            move_layout.addWidget(down_btn)
            self._steps_table.setCellWidget(row, 5, move_widget)

            delete = self._make_delete_button("删除步骤")
            delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
            self._steps_table.setCellWidget(row, 6, delete)
        self._fit_steps_table_to_content()

    def _fit_steps_table_to_content(self) -> None:
        if not hasattr(self, "_steps_table"):
            return

        table = self._steps_table
        if table.columnCount() == 0:
            return

        metrics = table.fontMetrics()
        header_metrics = table.horizontalHeader().fontMetrics()

        def text_width(text: str, padding: int = 40) -> int:
            return max(metrics.horizontalAdvance(text), header_metrics.horizontalAdvance(text)) + padding

        headers = [
            table.horizontalHeaderItem(column).text()
            if table.horizontalHeaderItem(column) is not None
            else ""
            for column in range(table.columnCount())
        ]
        natural = [
            text_width(headers[0], 34),
            text_width(headers[1], 40),
            text_width(headers[2], 48),
            text_width(headers[3], 48),
            text_width(headers[4], 48),
            92,
            52,
        ]

        for row in range(table.rowCount()):
            natural[0] = max(natural[0], text_width(self._table_text(table, row, 0), 36))
            action_combo = table.cellWidget(row, 1)
            if isinstance(action_combo, QComboBox):
                natural[1] = max(natural[1], text_width(action_combo.currentText(), 42))
            natural[2] = max(natural[2], text_width(self._table_text(table, row, 2), 48))
            natural[3] = max(natural[3], text_width(self._table_text(table, row, 3), 48))
            natural[4] = max(natural[4], text_width(self._condition_summary(self._row_condition(row)), 54))
            table.setRowHeight(row, _STEP_TABLE_BASE_ROW_HEIGHT)

        mins = [110, 150, 170, 90, 150, 92, 52]
        maxes = [190, 240, 360, 420, 380, 92, 52]
        widths = [min(max(natural[i], mins[i]), maxes[i]) for i in range(table.columnCount())]

        available = table.viewport().width()
        if available <= 0:
            available = table.width() - table.verticalHeader().width() - 2
        fixed_width = widths[0] + widths[1] + widths[5] + widths[6]
        grow_columns = [2, 3, 4]
        grow_width = available - fixed_width
        if grow_width > sum(widths[column] for column in grow_columns):
            extra = grow_width - sum(widths[column] for column in grow_columns)
            for column, weight in ((2, 0.35), (3, 0.30), (4, 0.35)):
                widths[column] += int(extra * weight)
        elif available > 0 and sum(widths) > available:
            deficit = sum(widths) - available
            for column in (4, 3, 2, 0, 1):
                shrink = min(deficit, widths[column] - mins[column])
                if shrink <= 0:
                    continue
                widths[column] -= shrink
                deficit -= shrink
                if deficit <= 0:
                    break

        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)

        visible_rows = max(1, min(table.rowCount(), _STEP_TABLE_MAX_VISIBLE_ROWS))
        header_height = table.horizontalHeader().height()
        frame = table.frameWidth() * 2
        horizontal_scroll_height = table.horizontalScrollBar().sizeHint().height()
        target_height = (
            header_height
            + visible_rows * _STEP_TABLE_BASE_ROW_HEIGHT
            + frame
            + horizontal_scroll_height
            + 10
        )
        table.setMinimumHeight(target_height)
        table.setMaximumHeight(target_height if table.rowCount() <= _STEP_TABLE_MAX_VISIBLE_ROWS else 16777215)

    def _collect_steps(self) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []
        for row in range(self._steps_table.rowCount()):
            step_id = self._table_text(self._steps_table, row, 0)
            action_combo = self._steps_table.cellWidget(row, 1)
            action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
            anchor_id = self._table_text(self._steps_table, row, 2) or None
            value_text = self._table_text(self._steps_table, row, 3)
            value = value_text if value_text else None
            condition = self._row_condition(row)
            if not step_id:
                raise ValueError("步骤 ID 不能为空")
            if not action:
                raise ValueError(f"步骤 {step_id} 未选择动作")
            step_payload = {
                "id": step_id,
                "action": action,
                "anchor_id": anchor_id,
                "value": value,
            }
            if condition:
                step_payload["expected_text"] = condition.get("expected_text") or None
                step_payload["match_mode"] = condition.get("match_mode") or "none"
                step_payload["timeout_seconds"] = condition.get("timeout_seconds")
            steps.append(
                WorkflowStep(**step_payload)
            )
        return steps

    # --- combo/data helpers --------------------------------------------- #
    def _anchor_choices(self) -> list[str]:
        profile = self._vm.get_anchor_profile(self._anchor_profile.currentText() or None)
        if profile is None:
            return []
        anchors = list(profile.anchors)
        anchors.sort(key=lambda a: (a.observe_region is None, a.id))
        return [anchor.id for anchor in anchors]

    def _first_anchor_choice(self) -> str:
        choices = self._anchor_choices()
        return choices[0] if choices else ""

    @staticmethod
    def _make_icon_button(
        text: str, *, object_name: str, tooltip: str, width: int = 32
    ) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setFixedSize(width, 30)
        return button

    def _make_delete_button(self, tooltip: str) -> QPushButton:
        return self._make_icon_button(_DELETE_GLYPH, object_name="Danger", tooltip=tooltip)

    @staticmethod
    def _table_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item else ""

    @staticmethod
    def _combo_text(table: QTableWidget, row: int, column: int) -> str:
        combo = table.cellWidget(row, column)
        return combo.currentText().strip() if isinstance(combo, QComboBox) else ""

    # --- save / standardize --------------------------------------------- #
    def _build_form_workflow(self) -> WorkflowContract:
        if self._current is None:
            raise ValueError("请先生成或选择一个工作流")
        steps = self._collect_steps()
        workflow = self._current.model_copy(deep=True)
        anchor_profile = self._anchor_profile.currentText().strip()
        if anchor_profile and anchor_profile != "unknown_device":
            workflow.metadata = _metadata_with_anchor_profile(workflow.metadata, anchor_profile)
        workflow.steps = steps
        workflow.roi_bindings = {}
        workflow.outputs = []
        return workflow

    def _save_workflow(self) -> None:
        try:
            workflow = self._build_form_workflow()
            saved = self._vm.save_workflow(workflow)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._current = saved
        self._populate_steps_table(saved)
        self._reload()
        self._precheck.setText(
            "<span style='color:%s;font-weight:600;'>已保存工作流配置。</span>" % t.SUCCESS
        )
        QMessageBox.information(self, "保存成功", f"已保存工作流: {saved.metadata.workflow_id}")

    def _standardize(self) -> None:
        try:
            workflow = self._build_form_workflow()
        except Exception as exc:  # noqa: BLE001
            self._precheck.setText(f"<span style='color:{t.WARNING};'>{exc}</span>")
            return
        self._current = workflow
        result = self._vm.standardize(workflow)
        if result.ok:
            self._precheck.setText(
                f"<span style='color:{t.SUCCESS};font-weight:600;'>✓ 通过标准化检查，可进入 Standardized。</span>"
            )
            return
        rows = [f"<div style='color:{t.DANGER};font-weight:600;'>✕ 未通过，需修复：</div>"]
        for issue in result.issues:
            rows.append(f"<div style='color:{t.INK_MUTED};margin:3px 0;'>· {issue}</div>")
        self._precheck.setText("".join(rows))
