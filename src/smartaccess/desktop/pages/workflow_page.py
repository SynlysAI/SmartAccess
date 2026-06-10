"""Workflow design page: AI draft, context references, reasoning trace, and editable steps."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, unquote

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
    QStackedWidget,
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
from smartaccess.desktop.workflow_projection import (
    REFERENCE_CATEGORY_LABELS,
    REFERENCE_CATEGORY_ORDER,
    WorkflowContextSnapshot,
    build_context_snapshot,
)
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowOutput, WorkflowStep

_ACTION_NOTES = {
    "click": "单击控件",
    "double_click": "双击控件",
    "type": "输入文本",
    "press_enter": "按回车键",
    "hotkey": "发送快捷键",
    "wait": "固定等待",
    "wait_until": "轮询直到条件满足",
    "screenshot_check": "截图校验",
}
_OBSERVATION_TYPES = {"observation", "readout", "status", "region", "roi"}
_MOVE_UP_GLYPH = "↑"
_MOVE_DOWN_GLYPH = "↓"
_DELETE_GLYPH = "×"
_TAB_NAME_TO_INDEX = {"steps": 0, "bindings": 1, "outputs": 2}
_PROMPT_REFERENCE_RE = re.compile(r"@(?:field:|confirm:)?[A-Za-z0-9_]+")
_DEFAULT_PROMPT = "打开方法编辑器，设定目标参数，启动运行并等待状态变化。"
_LEFT_MODE_DRAFT = 0
_LEFT_MODE_REVIEW = 1


def _ordered_unique_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _PROMPT_REFERENCE_RE.finditer(text or ""):
        token = match.group(0)
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


class WorkflowPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = WorkflowViewModel(facade, self)
        self._current: WorkflowContract | None = None
        self._loading = False
        self._syncing_prompt = False
        self._context_snapshot = build_context_snapshot(None)
        self._active_reference_tokens: list[str] = []
        self._invalid_reference_tokens: list[str] = []
        self._reference_category = "observation"
        self._step_conditions: dict[int, dict] = {}

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
        self._draft_panel_toggle.setChecked(True)
        self._draft_panel_toggle.setToolTip("显示或隐藏左侧 AI 助手面板。")
        header_row.addWidget(self._draft_panel_toggle)
        self._review_panel_toggle = QPushButton("审阅面板")
        self._review_panel_toggle.setObjectName("Ghost")
        self._review_panel_toggle.setCheckable(True)
        self._review_panel_toggle.setChecked(True)
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
        root.addWidget(self._inner, 1)

        self._draft_panel_toggle.toggled.connect(self._draft_dock.setVisible)
        self._draft_dock.visibilityChanged.connect(self._draft_panel_toggle.setChecked)
        self._review_panel_toggle.toggled.connect(self._review_dock.setVisible)
        self._review_dock.visibilityChanged.connect(self._review_panel_toggle.setChecked)

        self._reload()
        self._set_prompt_text(_DEFAULT_PROMPT)

    def on_show(self) -> None:
        self._reload()
        if self._current is not None:
            self._refresh_context_panel()
            self._refresh_reasoning_view()

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
        left.add(self._build_left_mode_toggle())

        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._build_draft_mode())
        left.body().addWidget(self._left_stack, 1)
        self._set_left_mode(_LEFT_MODE_DRAFT)
        return left

    def _build_left_mode_toggle(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._left_mode_group = QButtonGroup(self)
        self._left_mode_group.setExclusive(True)
        self._draft_mode_btn = QPushButton("起草")
        self._draft_mode_btn.setObjectName("Segment")
        self._draft_mode_btn.setCheckable(True)
        self._review_mode_btn = QPushButton("审阅")
        self._review_mode_btn.setObjectName("Segment")
        self._review_mode_btn.setCheckable(True)
        self._left_mode_group.addButton(self._draft_mode_btn, _LEFT_MODE_DRAFT)
        self._left_mode_group.addButton(self._review_mode_btn, _LEFT_MODE_REVIEW)
        self._left_mode_group.idClicked.connect(self._set_left_mode)

        row.addWidget(self._draft_mode_btn)
        row.addWidget(self._review_mode_btn)
        row.addStretch(1)
        return box

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

        device_box = QWidget()
        device_layout = QVBoxLayout(device_box)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(6)
        self._device_label = QLabel("目标设备")
        self._device_label.setObjectName("Body")
        self._device = QComboBox()
        self._device.currentIndexChanged.connect(self._on_device_changed)
        device_layout.addWidget(self._device_label)
        device_layout.addWidget(self._device)

        meta_row.addWidget(workflow_box, 1)
        meta_row.addWidget(device_box, 1)
        layout.addWidget(meta)

        self._prompt_label = QLabel("自动化目标")
        self._prompt_label.setObjectName("Body")
        layout.addWidget(self._prompt_label)
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("描述要完成的实验或操作流程，可插入下方设备信息引用以明确目标区域。")
        self._prompt.setMaximumHeight(150)
        self._prompt.textChanged.connect(self._on_prompt_changed)
        layout.addWidget(self._prompt)

        layout.addWidget(section_title("已引用设备信息"))
        layout.addWidget(hint_label("自动化目标中使用的设备信息会显示在这里，可直接移除。"))
        self._reference_bar = QTextBrowser()
        self._reference_bar.setOpenLinks(False)
        self._reference_bar.setOpenExternalLinks(False)
        self._reference_bar.anchorClicked.connect(self._handle_reference_bar_link)
        self._reference_bar.setMaximumHeight(96)
        layout.addWidget(self._reference_bar)
        self._actual_reference_bar = QTextBrowser()
        self._actual_reference_bar.setOpenLinks(False)
        self._actual_reference_bar.setOpenExternalLinks(False)
        self._actual_reference_bar.setMaximumHeight(92)
        layout.addWidget(self._actual_reference_bar)

        layout.addWidget(section_title("设备信息引用"))
        layout.addWidget(hint_label("按类别筛选设备信息。点击引用项会插入到自动化目标中。"))
        layout.addWidget(self._build_reference_filters())

        self._reference_panel = QTextBrowser()
        self._reference_panel.setOpenLinks(False)
        self._reference_panel.setOpenExternalLinks(False)
        self._reference_panel.anchorClicked.connect(self._handle_reference_panel_link)
        self._reference_panel.setMinimumHeight(240)
        layout.addWidget(self._reference_panel, 1)

        generate = QPushButton("生成草稿")
        generate.clicked.connect(self._generate)
        layout.addWidget(generate)
        return page

    def _build_reference_filters(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._reference_filter_group = QButtonGroup(self)
        self._reference_filter_group.setExclusive(True)
        self._reference_filter_buttons: dict[str, QPushButton] = {}
        for category in REFERENCE_CATEGORY_ORDER:
            button = QPushButton(REFERENCE_CATEGORY_LABELS[category])
            button.setObjectName("Segment")
            button.setCheckable(True)
            self._reference_filter_group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, chosen=category: self._set_reference_category(chosen)
            )
            self._reference_filter_buttons[category] = button
            row.addWidget(button)
        row.addStretch(1)
        return box

    def _build_review_mode(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        self._reasoning_section = CollapsibleSection("生成说明", expanded=True)
        self._reasoning_section.add(hint_label("展示 AI 助手使用了哪些设备信息，以及生成了哪些步骤。"))
        self._reasoning = QTextBrowser()
        self._reasoning.setObjectName("LogView")
        self._reasoning_section.add(self._reasoning)
        layout.addWidget(self._reasoning_section)

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
        review.add(section_title("生成记录"))
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
        self._steps_table.setHorizontalHeaderLabels(["步骤 ID", "动作", "目标", "值", "条件", "上移/下移", ""])
        self._steps_table.verticalHeader().setDefaultSectionSize(52)
        steps_header = self._steps_table.horizontalHeader()
        steps_header.setStretchLastSection(False)
        steps_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._steps_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._steps_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._steps_table.setColumnWidth(0, 190)
        self._steps_table.setColumnWidth(1, 170)
        self._steps_table.setColumnWidth(2, 260)
        self._steps_table.setColumnWidth(3, 280)
        self._steps_table.setColumnWidth(4, 240)
        self._steps_table.setColumnWidth(5, 92)
        self._steps_table.setColumnWidth(6, 48)
        self._steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._steps_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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

        bindings_page = QWidget()
        bindings_layout = QVBoxLayout(bindings_page)
        bindings_layout.setContentsMargins(12, 12, 12, 12)
        bindings_layout.setSpacing(8)
        bindings_layout.addWidget(
            hint_label("ROI 绑定 = 工作流逻辑名 -> 已校准锚点。两个工作流可以复用同一个设备锚点；左侧名称描述本流程里的用途，右侧锚点来自仪器画像。")
        )
        self._binding_table = QTableWidget(0, 3)
        self._binding_table.setHorizontalHeaderLabels(["绑定名", "锚点 / ROI", ""])
        self._binding_table.verticalHeader().setDefaultSectionSize(52)
        binding_header = self._binding_table.horizontalHeader()
        binding_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        binding_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        binding_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._binding_table.setColumnWidth(2, 44)
        bindings_layout.addWidget(self._binding_table, 1)
        binding_controls = QWidget()
        binding_row = QHBoxLayout(binding_controls)
        binding_row.setContentsMargins(0, 0, 0, 0)
        add_binding = QPushButton("+ 添加绑定")
        add_binding.setObjectName("Ghost")
        add_binding.clicked.connect(self._add_binding_row)
        binding_row.addWidget(add_binding)
        fill_bindings = QPushButton("从仪器锚点填充")
        fill_bindings.setObjectName("Ghost")
        fill_bindings.clicked.connect(self._fill_bindings_from_anchors)
        binding_row.addWidget(fill_bindings)
        binding_row.addStretch(1)
        bindings_layout.addWidget(binding_controls)
        self._editor_tabs.addTab(bindings_page, "ROI 绑定")

        outputs_page = QWidget()
        outputs_layout = QVBoxLayout(outputs_page)
        outputs_layout.setContentsMargins(12, 12, 12, 12)
        outputs_layout.setSpacing(8)
        outputs_layout.addWidget(
            hint_label("声明工作流完成后要保留的结果：输出 Key 是结果名，来源可选择 ROI 绑定名或具体锚点，后续由 OCR / presence / template / color 观测写入。")
        )
        self._output_table = QTableWidget(0, 3)
        self._output_table.setHorizontalHeaderLabels(["输出 Key", "来源", ""])
        self._output_table.verticalHeader().setDefaultSectionSize(52)
        output_header = self._output_table.horizontalHeader()
        output_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        output_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        output_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._output_table.setColumnWidth(2, 44)
        outputs_layout.addWidget(self._output_table, 1)
        output_controls = QWidget()
        output_row = QHBoxLayout(output_controls)
        output_row.setContentsMargins(0, 0, 0, 0)
        add_output = QPushButton("+ 添加输出")
        add_output.setObjectName("Ghost")
        add_output.clicked.connect(self._add_output_row)
        output_row.addWidget(add_output)
        fill_outputs = QPushButton("从 ROI 绑定生成输出")
        fill_outputs.setObjectName("Ghost")
        fill_outputs.clicked.connect(self._fill_outputs_from_bindings)
        output_row.addWidget(fill_outputs)
        output_row.addStretch(1)
        outputs_layout.addWidget(output_controls)
        self._editor_tabs.addTab(outputs_page, "输出项")

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
        current_device = self._device.currentText() if hasattr(self, "_device") else ""
        self._loading = True
        self._device.clear()
        self._device.addItems(self._vm.list_instrument_ids() or ["unknown_device"])
        if current_device:
            idx = self._device.findText(current_device)
            if idx >= 0:
                self._device.setCurrentIndex(idx)
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
                device_id=self._device.currentText() or None,
                workflow_id=self._workflow_id.text().strip() or "wf_new_experiment",
                prompt_references=self._context_snapshot.structured_prompt_references(
                    self._active_reference_tokens
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._refresh_reasoning_view(error=exc)
            self._set_left_mode(_LEFT_MODE_REVIEW)
            QMessageBox.critical(self, "生成失败", str(exc))
            return
        self._show_workflow(workflow)
        self._reload()
        self._set_left_mode(_LEFT_MODE_REVIEW)

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
        self._sync_device_to_workflow(workflow)
        self._refresh_context_panel()
        self._restore_prompt_for_workflow(workflow)
        self._populate_steps_table(workflow)
        self._populate_binding_table(workflow)
        self._populate_output_table(workflow)
        self._refresh_context_panel()
        self._refresh_reasoning_view()
        self._precheck.setText("已加载工作流，可编辑步骤、 ROI 绑定和输出项后保存或运行标准化检查。")

    def _restore_prompt_for_workflow(self, workflow: WorkflowContract) -> None:
        record = self._vm.draft_record(workflow.metadata.workflow_id)
        prompt = record.prompt if record is not None else ""
        self._set_prompt_text(prompt or "")

    def _sync_device_to_workflow(self, workflow: WorkflowContract) -> None:
        device_id = workflow.metadata.instrument_profile
        idx = self._device.findText(device_id)
        if idx >= 0:
            self._loading = True
            self._device.setCurrentIndex(idx)
            self._loading = False

    def _on_device_changed(self) -> None:
        if self._loading:
            return
        self._refresh_context_panel()
        self._refresh_reasoning_view()
        if self._current is not None:
            self._refresh_binding_combos()
            self._refresh_output_combos()

    def _on_prompt_changed(self) -> None:
        if self._syncing_prompt:
            return
        self._set_left_mode(_LEFT_MODE_DRAFT)
        self._sync_prompt_reference_state()

    def _set_prompt_text(self, text: str) -> None:
        self._syncing_prompt = True
        blocker = QSignalBlocker(self._prompt)
        self._prompt.setPlainText(text)
        del blocker
        self._syncing_prompt = False
        self._sync_prompt_reference_state()

    def _sync_prompt_reference_state(self) -> None:
        tokens = _ordered_unique_tokens(self._prompt.toPlainText())
        refs = self._context_snapshot.reference_map()
        self._active_reference_tokens = [token for token in tokens if token in refs]
        self._invalid_reference_tokens = [token for token in tokens if token not in refs]
        self._refresh_reference_bar()
        self._refresh_actual_reference_bar()
        self._refresh_reference_panel()
        self._refresh_reasoning_view()

    def _set_left_mode(self, mode: int) -> None:
        self._left_stack.setCurrentIndex(_LEFT_MODE_DRAFT)
        draft_blocker = QSignalBlocker(self._draft_mode_btn)
        review_blocker = QSignalBlocker(self._review_mode_btn)
        self._draft_mode_btn.setChecked(True)
        self._review_mode_btn.setChecked(False)
        del draft_blocker
        del review_blocker

    def _set_reference_category(self, category: str) -> None:
        if category not in REFERENCE_CATEGORY_ORDER:
            return
        if not self._context_snapshot.has_category(category):
            return
        self._reference_category = category
        self._refresh_reference_filters()
        self._refresh_reference_panel()

    def _preferred_reference_category(self) -> str:
        if self._context_snapshot.has_category("observation"):
            return "observation"
        if self._context_snapshot.has_category("action"):
            return "action"
        for category in REFERENCE_CATEGORY_ORDER:
            if self._context_snapshot.has_category(category):
                return category
        return "observation"

    def _refresh_reference_filters(self) -> None:
        if not self._context_snapshot.has_category(self._reference_category):
            self._reference_category = self._preferred_reference_category()
        for category, button in self._reference_filter_buttons.items():
            count = len(self._context_snapshot.items_for_category(category))
            button.setText(
                f"{REFERENCE_CATEGORY_LABELS[category]} ({count})" if count else REFERENCE_CATEGORY_LABELS[category]
            )
            button.setEnabled(count > 0)
            blocker = QSignalBlocker(button)
            button.setChecked(category == self._reference_category and count > 0)
            del blocker

    def _refresh_context_panel(self) -> None:
        profile = self._vm.get_instrument(self._device.currentText() or None)
        self._context_snapshot = build_context_snapshot(profile)
        self._refresh_reference_filters()
        self._sync_prompt_reference_state()

    def _refresh_reference_panel(self) -> None:
        self._reference_panel.setHtml(
            self._context_snapshot.to_reference_panel_html(
                self._reference_category,
                active_tokens=set(self._active_reference_tokens),
                interactive=True,
            )
        )

    def _refresh_reference_bar(self) -> None:
        if not self._active_reference_tokens and not self._invalid_reference_tokens:
            self._reference_bar.setHtml(
                f"<span style='color:{t.INK_SUBTLE};'>尚未引用设备信息。点击下方引用项可快速插入。</span>"
            )
            return
        refs = self._context_snapshot.reference_map()
        chips: list[str] = []
        for token in self._active_reference_tokens:
            item = refs[token]
            chips.append(self._render_reference_chip(token, item.title, invalid=False, removable=True))
        for token in self._invalid_reference_tokens:
            chips.append(self._render_reference_chip(token, "未匹配当前设备", invalid=True, removable=False))
        self._reference_bar.setHtml("".join(chips))

    def _render_reference_chip(
        self, token: str, title: str, *, invalid: bool, removable: bool
    ) -> str:
        bg = "#2a1417" if invalid else t.PRIMARY_SOFT
        border = t.DANGER if invalid else t.PRIMARY
        token_fg = t.DANGER if invalid else t.PRIMARY_HOVER
        title_fg = t.INK_SUBTLE if invalid else t.INK_MUTED
        remove_html = ""
        if removable:
            remove_html = (
                f"<a href='remove:{quote(token, safe='')}' "
                f"style='margin-left:8px;color:{t.INK};text-decoration:none;font-weight:700;'>×</a>"
            )
        return (
            f"<span style='display:inline-block;margin:4px 6px 4px 0;padding:8px 10px;"
            f"border-radius:999px;border:1px solid {border};background:{bg};'>"
            f"<span style='color:{token_fg};font-weight:700;'>{html.escape(token)}</span>"
            f"<span style='color:{title_fg};'> · {html.escape(title)}</span>"
            f"{remove_html}</span>"
        )

    def _refresh_actual_reference_bar(self) -> None:
        refs = self._context_snapshot.reference_map()
        rows = self._record_reference_rows()
        if not rows:
            self._actual_reference_bar.setHtml(
                f"<span style='color:{t.INK_SUBTLE};'>暂无本次生成实际带入的引用记录。</span>"
            )
            return
        chips: list[str] = []
        for row in rows:
            token = row.get("token", "")
            title = row.get("ref_id", token)
            if token in refs:
                title = refs[token].title
            chips.append(
                self._render_reference_chip(token, title, invalid=False, removable=False)
            )
        self._actual_reference_bar.setHtml(
            f"<div style='color:{t.INK_SUBTLE};margin-bottom:4px;'>本次生成实际带入：</div>"
            + "".join(chips)
        )

    def _record_reference_rows(self) -> list[dict[str, str]]:
        if self._current is None:
            return []
        record = self._vm.draft_record(self._current.metadata.workflow_id)
        if record is None:
            return []
        rows: list[dict[str, str]] = []
        for row in record.context.get("prompt_references") or []:
            if isinstance(row, dict):
                rows.append(
                    {
                        "token": str(row.get("token") or ""),
                        "category": str(row.get("category") or ""),
                        "ref_id": str(row.get("ref_id") or ""),
                    }
                )
        return rows

    def _handle_reference_panel_link(self, url) -> None:
        text = url.toString()
        if not text.startswith("insert:"):
            return
        token = unquote(text.split(":", 1)[1])
        self._insert_prompt_reference(token)

    def _handle_reference_bar_link(self, url) -> None:
        text = url.toString()
        if not text.startswith("remove:"):
            return
        token = unquote(text.split(":", 1)[1])
        self._remove_prompt_reference(token)

    def _insert_prompt_reference(self, token: str) -> None:
        match = self._find_reference_span(self._prompt.toPlainText(), token)
        if match is not None:
            cursor = self._prompt.textCursor()
            cursor.setPosition(match[1])
            self._prompt.setTextCursor(cursor)
            self._prompt.setFocus()
            self._sync_prompt_reference_state()
            return

        cursor = self._prompt.textCursor()
        text = self._prompt.toPlainText()
        pos = cursor.position()
        before = text[pos - 1] if pos > 0 else ""
        after = text[pos] if pos < len(text) else ""
        prefix = "" if not before or before.isspace() else " "
        suffix = "" if not after or after.isspace() else " "
        cursor.insertText(f"{prefix}{token}{suffix}")
        self._prompt.setTextCursor(cursor)
        self._prompt.setFocus()
        self._set_left_mode(_LEFT_MODE_DRAFT)

    def _remove_prompt_reference(self, token: str) -> None:
        pattern = self._reference_regex(token)
        new_text = pattern.sub(" ", self._prompt.toPlainText())
        new_text = re.sub(r"[ \t]{2,}", " ", new_text)
        new_text = re.sub(r" *\n *", "\n", new_text)
        self._set_prompt_text(new_text.strip())
        self._prompt.setFocus()
        self._set_left_mode(_LEFT_MODE_DRAFT)

    @staticmethod
    def _reference_regex(token: str) -> re.Pattern[str]:
        return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")

    def _find_reference_span(self, text: str, token: str) -> tuple[int, int] | None:
        match = self._reference_regex(token).search(text)
        if match is None:
            return None
        return match.start(), match.end()

    def _refresh_reasoning_view(self, error: Exception | None = None) -> None:
        active_tokens = set(self._active_reference_tokens)
        if self._current is not None:
            record = self._vm.draft_record(self._current.metadata.workflow_id)
            if record is not None:
                device_id = record.context.get("instrument_profile") or None
                profile = self._vm.get_instrument(device_id)
                snapshot = build_context_snapshot(profile)
                reasoning = record.reasoning or "_本次生成未提供推理过程。_"
                self._reasoning.setMarkdown(
                    f"{snapshot.to_markdown(active_tokens=active_tokens)}\n\n---\n\n{reasoning}"
                )
                return
            self._reasoning.setMarkdown(
                f"{self._context_snapshot.to_markdown(active_tokens=active_tokens)}\n\n---\n\n_尚无本工作流的 AI 推理记录。_"
            )
            return
        if error is not None:
            self._reasoning.setMarkdown(
                f"{self._context_snapshot.to_markdown(active_tokens=active_tokens)}\n\n---\n\n## 生成失败\n\n```\n{error}\n```"
            )
            return
        self._reasoning.setMarkdown("_生成草稿后，这里会显示上下文快照和编排推理过程。_")

    # --- editable steps --------------------------------------------------- #
    def _populate_steps_table(self, workflow: WorkflowContract) -> None:
        self._steps_table.setRowCount(0)
        self._step_conditions: dict[int, dict] = {}
        for step in workflow.steps:
            row = self._steps_table.rowCount()
            self._insert_step_row(step.id, step.action, step.target or "", step.value or "")
            if step.condition:
                self._step_conditions[row] = dict(step.condition)

    def _add_step_row(self) -> None:
        step_num = self._steps_table.rowCount() + 1
        self._insert_step_row(f"step_{step_num}", "click", "", "")
        self._renumber_steps()

    def _insert_step_after_selection(self) -> None:
        selected = self._steps_table.currentRow()
        if selected < 0 or selected >= self._steps_table.rowCount():
            self._add_step_row()
            return
        step_num = self._steps_table.rowCount() + 1
        self._insert_step_at(f"step_{step_num}", "click", "", "", selected + 1)
        self._renumber_steps()

    def _insert_step_at(
        self, step_id: str, action: str, target: str, value: str, row: int
    ) -> None:
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, QTableWidgetItem(step_id))

        action_combo = QComboBox()
        action_combo.setMinimumHeight(34)
        for act_key, act_label in _ACTION_NOTES.items():
            action_combo.addItem(f"{act_key} · {act_label}", act_key)
        idx = action_combo.findData(action)
        if idx >= 0:
            action_combo.setCurrentIndex(idx)
        self._steps_table.setCellWidget(row, 1, action_combo)

        self._steps_table.setItem(row, 2, QTableWidgetItem(target))
        self._steps_table.setItem(row, 3, QTableWidgetItem(str(value)))

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

    def _insert_step_row(self, step_id: str, action: str, target: str, value: str) -> None:
        row = self._steps_table.rowCount()
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, QTableWidgetItem(step_id))

        action_combo = QComboBox()
        action_combo.setMinimumHeight(34)
        for act_key, act_label in _ACTION_NOTES.items():
            action_combo.addItem(f"{act_key} · {act_label}", act_key)
        idx = action_combo.findData(action)
        if idx >= 0:
            action_combo.setCurrentIndex(idx)
        self._steps_table.setCellWidget(row, 1, action_combo)
        self._steps_table.setItem(row, 2, QTableWidgetItem(target))
        self._steps_table.setItem(row, 3, QTableWidgetItem(str(value)))

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

    def _delete_step_row(self, row: int) -> None:
        self._steps_table.removeRow(row)
        self._step_conditions = {
            (idx - 1 if idx > row else idx): condition
            for idx, condition in self._step_conditions.items()
            if idx != row
        }
        self._rebind_step_buttons()
        self._renumber_steps()

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
        # Swap conditions too
        cond1 = self._step_conditions.pop(row1, None)
        cond2 = self._step_conditions.pop(row2, None)
        if cond2 is not None:
            self._step_conditions[row1] = cond2
        if cond1 is not None:
            self._step_conditions[row2] = cond1
        self._renumber_steps()

    def _renumber_steps(self) -> None:
        for row in range(self._steps_table.rowCount()):
            item = self._steps_table.item(row, 0)
            if item is not None:
                item.setText(f"step_{row + 1}")

    def _edit_condition(self, row: int) -> None:
        """Open the condition editor for a step row."""
        from smartaccess.desktop.widgets.condition_editor import ConditionEditorDialog

        sources = self._source_choices()
        current = self._step_conditions.get(row)
        dlg = ConditionEditorDialog(current, available_sources=sources, parent=self)
        if dlg.exec() == ConditionEditorDialog.DialogCode.Accepted:
            condition = dlg.condition_dict()
            self._step_conditions[row] = condition
            self._steps_table.setCellWidget(row, 4, self._make_condition_button(row))

    def _make_condition_button(self, row: int) -> QPushButton:
        summary = self._condition_summary(self._step_conditions.get(row))
        button = QPushButton(summary)
        button.setObjectName("Ghost")
        button.setToolTip("编辑观测条件 (source/mode/operator/timeout_seconds)")
        button.setMinimumHeight(30)
        button.setMaximumWidth(210)
        button.clicked.connect(lambda _checked=False, r=row: self._edit_condition(r))
        return button

    @staticmethod
    def _condition_summary(condition: dict | None) -> str:
        if not condition:
            return "未配置"
        source = str(condition.get("source") or condition.get("roi") or "-")
        mode = str(condition.get("mode") or "ocr")
        operator = str(condition.get("operator") or "exists")
        expected = str(condition.get("expected") or "")
        timeout = condition.get("timeout_seconds") or condition.get("timeout") or ""
        main = f"{source} · {mode} · {operator}"
        if expected:
            main = f"{main} {expected}"
        if timeout:
            main = f"{main} · {timeout}s"
        return main

    def _collect_step_row_data(self, row: int) -> tuple[str, str, str, str]:
        step_id = self._table_text(self._steps_table, row, 0)
        action_combo = self._steps_table.cellWidget(row, 1)
        action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
        target = self._table_text(self._steps_table, row, 2)
        value = self._table_text(self._steps_table, row, 3)
        return (step_id, action, target, value)

    def _set_step_row_data(self, row: int, data: tuple[str, str, str, str]) -> None:
        step_id, action, target, value = data
        self._steps_table.item(row, 0).setText(step_id)
        action_combo = self._steps_table.cellWidget(row, 1)
        if isinstance(action_combo, QComboBox):
            idx = action_combo.findData(action)
            if idx >= 0:
                action_combo.setCurrentIndex(idx)
        self._steps_table.item(row, 2).setText(target)
        self._steps_table.item(row, 3).setText(value)

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

    def _collect_steps(self) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []
        for row in range(self._steps_table.rowCount()):
            step_id = self._table_text(self._steps_table, row, 0)
            action_combo = self._steps_table.cellWidget(row, 1)
            action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
            target = self._table_text(self._steps_table, row, 2) or None
            value_text = self._table_text(self._steps_table, row, 3)
            value = value_text if value_text else None
            condition = self._step_conditions.get(row)
            if not step_id:
                raise ValueError("步骤 ID 不能为空")
            if not action:
                raise ValueError(f"步骤 {step_id} 未选择动作")
            steps.append(WorkflowStep(id=step_id, action=action, target=target, value=value, condition=condition))
        return steps

    # --- editable ROI bindings ----------------------------------------- #
    def _populate_binding_table(self, workflow: WorkflowContract) -> None:
        self._binding_table.setRowCount(0)
        for name, target in workflow.roi_bindings.items():
            self._insert_binding_row(name, target)

    def _add_binding_row(self) -> None:
        self._insert_binding_row("", self._first_anchor_choice())

    def _insert_binding_row(self, name: str, target: str) -> None:
        row = self._binding_table.rowCount()
        self._binding_table.insertRow(row)
        self._binding_table.setItem(row, 0, QTableWidgetItem(name))
        self._binding_table.setCellWidget(row, 1, self._make_anchor_combo(target))
        delete = self._make_delete_button("删除绑定")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_binding_row(r))
        self._binding_table.setCellWidget(row, 2, delete)

    def _delete_binding_row(self, row: int) -> None:
        self._binding_table.removeRow(row)
        self._rebind_table_delete_buttons(self._binding_table, self._delete_binding_row)
        self._refresh_output_combos()

    def _fill_bindings_from_anchors(self) -> None:
        anchors = self._anchor_choices()
        if not anchors:
            QMessageBox.warning(self, "无可用锚点", "当前设备没有可用于绑定的锚点，请先完成设备校准。")
            return
        existing = {
            self._table_text(self._binding_table, row, 0)
            for row in range(self._binding_table.rowCount())
        }
        for anchor_id in anchors:
            if anchor_id not in existing:
                self._insert_binding_row(anchor_id, anchor_id)
        self._refresh_output_combos()

    def _collect_roi_bindings(self) -> dict[str, str]:
        bindings: dict[str, str] = {}
        valid_anchors = set(self._anchor_choices())
        for row in range(self._binding_table.rowCount()):
            name = self._table_text(self._binding_table, row, 0)
            combo = self._binding_table.cellWidget(row, 1)
            target = combo.currentText().strip() if isinstance(combo, QComboBox) else ""
            if not name:
                raise ValueError("ROI 绑定名不能为空")
            if name in bindings:
                raise ValueError(f"ROI 绑定名重复: {name}")
            if not target:
                raise ValueError(f"ROI 绑定 {name} 未选择锚点")
            if valid_anchors and target not in valid_anchors:
                raise ValueError(f"ROI 绑定 {name} 指向未校准锚点: {target}")
            bindings[name] = target
        return bindings

    # --- editable outputs ----------------------------------------------- #
    def _populate_output_table(self, workflow: WorkflowContract) -> None:
        self._output_table.setRowCount(0)
        for output in workflow.outputs:
            self._insert_output_row(output.key, output.source)

    def _add_output_row(self) -> None:
        self._insert_output_row("", self._first_output_source())

    def _insert_output_row(self, key: str, source: str) -> None:
        row = self._output_table.rowCount()
        self._output_table.insertRow(row)
        self._output_table.setItem(row, 0, QTableWidgetItem(key))
        self._output_table.setCellWidget(row, 1, self._make_source_combo(source))
        delete = self._make_delete_button("删除输出")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_output_row(r))
        self._output_table.setCellWidget(row, 2, delete)

    def _delete_output_row(self, row: int) -> None:
        self._output_table.removeRow(row)
        self._rebind_table_delete_buttons(self._output_table, self._delete_output_row)

    def _fill_outputs_from_bindings(self) -> None:
        try:
            bindings = self._collect_roi_bindings()
        except ValueError as exc:
            QMessageBox.warning(self, "ROI 绑定未完成", str(exc))
            return
        if not bindings:
            QMessageBox.warning(self, "无 ROI 绑定", "请先添加至少一个 ROI 绑定。")
            return
        existing = {
            self._table_text(self._output_table, row, 0)
            for row in range(self._output_table.rowCount())
        }
        for name, target in bindings.items():
            if name not in existing:
                self._insert_output_row(name, target)

    def _collect_outputs(self, bindings: dict[str, str]) -> list[WorkflowOutput]:
        outputs: list[WorkflowOutput] = []
        seen: set[str] = set()
        allowed_sources = set(bindings) | set(bindings.values()) | set(self._anchor_choices())
        for row in range(self._output_table.rowCount()):
            key = self._table_text(self._output_table, row, 0)
            combo = self._output_table.cellWidget(row, 1)
            source = combo.currentText().strip() if isinstance(combo, QComboBox) else ""
            if not key:
                raise ValueError("输出 Key 不能为空")
            if key in seen:
                raise ValueError(f"输出 Key 重复: {key}")
            if not source:
                raise ValueError(f"输出 {key} 未选择来源")
            if allowed_sources and source not in allowed_sources:
                raise ValueError(f"输出 {key} 的来源未绑定或未校准: {source}")
            outputs.append(WorkflowOutput(key=key, source=source))
            seen.add(key)
        return outputs

    # --- combo/data helpers --------------------------------------------- #
    def _anchor_choices(self) -> list[str]:
        profile = self._vm.get_instrument(self._device.currentText() or None)
        if profile is None:
            return []
        anchors = list(profile.anchors)
        anchors.sort(key=lambda a: (a.type not in _OBSERVATION_TYPES and a.vision_mode == "none", a.id))
        return [anchor.id for anchor in anchors]

    def _first_anchor_choice(self) -> str:
        choices = self._anchor_choices()
        return choices[0] if choices else ""

    def _source_choices(self) -> list[str]:
        choices: list[str] = []
        try:
            bindings = self._collect_roi_bindings()
        except ValueError:
            bindings = {}
        for value in [*bindings.keys(), *bindings.values(), *self._anchor_choices()]:
            if value and value not in choices:
                choices.append(value)
        return choices

    def _first_output_source(self) -> str:
        choices = self._source_choices()
        return choices[0] if choices else ""

    def _make_anchor_combo(self, current: str) -> QComboBox:
        return self._make_combo(self._anchor_choices(), current)

    def _make_source_combo(self, current: str) -> QComboBox:
        return self._make_combo(self._source_choices(), current)

    def _make_combo(self, choices: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setMinimumHeight(34)
        seen: set[str] = set()
        for choice in choices:
            if choice and choice not in seen:
                combo.addItem(choice)
                seen.add(choice)
        if current and current not in seen:
            combo.addItem(current)
        if current:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(current)
        return combo

    def _refresh_binding_combos(self) -> None:
        for row in range(self._binding_table.rowCount()):
            old = self._combo_text(self._binding_table, row, 1)
            self._binding_table.setCellWidget(row, 1, self._make_anchor_combo(old))

    def _refresh_output_combos(self) -> None:
        for row in range(self._output_table.rowCount()):
            old = self._combo_text(self._output_table, row, 1)
            self._output_table.setCellWidget(row, 1, self._make_source_combo(old))

    def _rebind_table_delete_buttons(self, table: QTableWidget, handler) -> None:
        for row in range(table.rowCount()):
            button = self._make_delete_button("删除此行")
            button.clicked.connect(lambda _checked=False, r=row: handler(r))
            table.setCellWidget(row, 2, button)

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
        bindings = self._collect_roi_bindings()
        outputs = self._collect_outputs(bindings)
        workflow = self._current.model_copy(deep=True)
        device_id = self._device.currentText().strip()
        if device_id and device_id != "unknown_device":
            workflow.metadata.instrument_profile = device_id
        workflow.steps = steps
        workflow.roi_bindings = bindings
        workflow.outputs = outputs
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
