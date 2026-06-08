"""Workflow design page: AI draft, reasoning trace, step orchestration, checks.

The right side stacks collapsible sections for steps, editable ROI bindings,
editable outputs, and standardization checks so workflows can be configured
without hand-editing YAML.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
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
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowOutput, WorkflowStep

# Plain-language notes for the action primitives, shown inline with each step.
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


class WorkflowPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = WorkflowViewModel(facade, self)
        self._current: WorkflowContract | None = None
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("工作流设计", "AI 生成、推理过程、锚点绑定、步骤编排与标准化"))

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_left(), 2)
        body.addWidget(self._build_right(), 3)
        root.addLayout(body, 1)

        self._reload()

    def on_show(self) -> None:
        self._reload()

    # ------------------------------------------------------------------ #
    def _build_left(self) -> QWidget:
        left = Card()
        left.add(section_title("AI 生成工作流"))
        self._gen_label = hint_label("")
        left.add(self._gen_label)
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("用自然语言描述实验步骤……")
        self._prompt.setPlainText("打开方法编辑器，设定目标参数，启动运行并等待状态变化。")
        self._prompt.setMaximumHeight(120)
        left.add(self._prompt)
        self._workflow_id = QLineEdit("wf_new_experiment")
        self._workflow_id.setPlaceholderText("工作流 ID")
        left.add(self._workflow_id)
        self._device = QComboBox()
        self._device.currentIndexChanged.connect(self._on_device_changed)
        left.add(self._device)
        generate = QPushButton("生成草稿")
        generate.clicked.connect(self._generate)
        left.add(generate)

        left.add(section_title("AI 分析与推理"))
        left.add(hint_label("展示模型/生成器如何读取上下文并编排步骤。"))
        self._reasoning = QTextBrowser()
        self._reasoning.setObjectName("LogView")
        self._reasoning.setMarkdown("_生成草稿后，这里会显示编排推理过程。_")
        left.add(self._reasoning)

        left.add(section_title("已有工作流"))
        self._workflows = QListWidget()
        self._workflows.itemSelectionChanged.connect(self._select_existing)
        left.add(self._workflows)
        return left

    def _build_right(self) -> QWidget:
        right = Card(flush=True)

        # ── Tab control for the three editors ──────────────────────────
        self._editor_tabs = QTabWidget()

        # ---- Tab 1: 步骤编排 -------------------------------------------
        steps_page = QWidget()
        steps_layout = QVBoxLayout(steps_page)
        steps_layout.setContentsMargins(12, 12, 12, 12)
        steps_layout.setSpacing(8)
        steps_layout.addWidget(
            hint_label("AI 生成的步骤可在此手动修改、调整顺序或删除。确认无误后保存工作流。")
        )
        self._steps_table = QTableWidget(0, 6)
        self._steps_table.setHorizontalHeaderLabels(["步骤 ID", "动作", "目标", "值", "上移/下移", ""])
        self._steps_table.verticalHeader().setDefaultSectionSize(48)
        steps_header = self._steps_table.horizontalHeader()
        steps_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        steps_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        steps_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        steps_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        steps_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        steps_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
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
        self._editor_tabs.addTab(steps_page, "📋 步骤编排")

        # ---- Tab 2: ROI 绑定 -------------------------------------------
        bindings_page = QWidget()
        bindings_layout = QVBoxLayout(bindings_page)
        bindings_layout.setContentsMargins(12, 12, 12, 12)
        bindings_layout.setSpacing(8)
        bindings_layout.addWidget(
            hint_label("把工作流里的逻辑名绑定到已校准锚点，运行时据此定位或读取区域。")
        )
        self._binding_table = QTableWidget(0, 3)
        self._binding_table.setHorizontalHeaderLabels(["绑定名", "锚点 / ROI", ""])
        self._binding_table.verticalHeader().setDefaultSectionSize(48)
        binding_header = self._binding_table.horizontalHeader()
        binding_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        binding_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        binding_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
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
        self._editor_tabs.addTab(bindings_page, "🎯 ROI 绑定")

        # ---- Tab 3: 输出项 ---------------------------------------------
        outputs_page = QWidget()
        outputs_layout = QVBoxLayout(outputs_page)
        outputs_layout.setContentsMargins(12, 12, 12, 12)
        outputs_layout.setSpacing(8)
        outputs_layout.addWidget(
            hint_label("声明工作流完成后要保留的结果，来源可选择 ROI 绑定名或具体锚点。")
        )
        self._output_table = QTableWidget(0, 3)
        self._output_table.setHorizontalHeaderLabels(["输出 Key", "来源", ""])
        self._output_table.verticalHeader().setDefaultSectionSize(48)
        output_header = self._output_table.horizontalHeader()
        output_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        output_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        output_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
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
        self._editor_tabs.addTab(outputs_page, "📤 输出项")

        right.add(self._editor_tabs)

        # ── Global actions ─────────────────────────────────────────────
        action_controls = QWidget()
        action_row = QHBoxLayout(action_controls)
        action_row.setContentsMargins(12, 8, 12, 4)
        action_row.addStretch(1)
        save = QPushButton("保存工作流配置")
        save.clicked.connect(self._save_workflow)
        action_row.addWidget(save)
        right.add(action_controls)

        # ── Precheck (always visible below the tabs) ────────────────────
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
        current_device = self._device.currentText()
        self._loading = True
        self._device.clear()
        self._device.addItems(self._vm.list_instrument_ids() or ["unknown_device"])
        if current_device:
            idx = self._device.findText(current_device)
            if idx >= 0:
                self._device.setCurrentIndex(idx)
        self._loading = False
        self._gen_label.setText(f"当前生成器：{self._vm.generator_label()}")
        selected_id = self._current.metadata.workflow_id if self._current else ""
        self._workflows.clear()
        selected_row = -1
        for row, wf in enumerate(self._vm.list_workflows()):
            self._workflows.addItem(f"{wf.metadata.workflow_id}  ·  {wf.metadata.lifecycle_state}")
            if wf.metadata.workflow_id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self._workflows.setCurrentRow(selected_row)

    def _generate(self) -> None:
        try:
            workflow = self._vm.generate(
                self._prompt.toPlainText(),
                device_id=self._device.currentText() or None,
                workflow_id=self._workflow_id.text().strip() or "wf_new_experiment",
            )
        except Exception as exc:  # noqa: BLE001
            self._reasoning.setMarkdown(self._vm.reasoning() or f"## 生成失败\n\n```\n{exc}\n```")
            QMessageBox.critical(self, "生成失败", str(exc))
            return
        self._reasoning.setMarkdown(self._vm.reasoning() or "_本次生成未提供推理过程。_")
        self._show_workflow(workflow)
        self._reload()

    def _select_existing(self) -> None:
        if self._loading:
            return
        idx = self._workflows.currentRow()
        workflows = self._vm.list_workflows()
        if 0 <= idx < len(workflows):
            self._show_workflow(workflows[idx])

    def _show_workflow(self, workflow: WorkflowContract) -> None:
        self._current = workflow
        self._sync_device_to_workflow(workflow)
        self._populate_steps_table(workflow)
        self._populate_binding_table(workflow)
        self._populate_output_table(workflow)
        self._precheck.setText("已加载工作流，可编辑步骤、ROI 绑定和输出项后保存或运行标准化检查。")

    def _sync_device_to_workflow(self, workflow: WorkflowContract) -> None:
        device_id = workflow.metadata.instrument_profile
        idx = self._device.findText(device_id)
        if idx >= 0:
            self._loading = True
            self._device.setCurrentIndex(idx)
            self._loading = False

    def _on_device_changed(self) -> None:
        if self._loading or self._current is None:
            return
        self._refresh_binding_combos()
        self._refresh_output_combos()

    def _render_steps(self, workflow: WorkflowContract) -> str:
        if not workflow.steps:
            return f"<span style='color:{t.INK_SUBTLE};'>该工作流暂无步骤。</span>"
        rows = [
            f"<div style='color:{t.INK_SUBTLE};margin-bottom:6px;'>"
            f"共 {len(workflow.steps)} 步 · 仪器 <b style='color:{t.INK};'>"
            f"{workflow.metadata.instrument_profile}</b></div>"
        ]
        for i, step in enumerate(workflow.steps, 1):
            note = _ACTION_NOTES.get(step.action, step.action)
            target = (f" → <span style='color:{t.PRIMARY_HOVER};'>{step.target}</span>"
                      if step.target else "")
            value = (f" <span style='color:{t.SUCCESS};'>= {step.value}</span>"
                     if step.value is not None else "")
            rows.append(
                f"<div style='margin:5px 0;line-height:150%;'>"
                f"<span style='color:{t.INK_SUBTLE};'>{i}.</span> "
                f"<b style='color:{t.INK};'>{step.id}</b>{target}{value}<br>"
                f"<span style='color:{t.INK_SUBTLE};font-size:12px;'>　{step.action} · {note}</span>"
                f"</div>"
            )
        return "".join(rows)

    # --- editable steps --------------------------------------------------- #
    def _populate_steps_table(self, workflow: WorkflowContract) -> None:
        self._steps_table.setRowCount(0)
        for step in workflow.steps:
            self._insert_step_row(step.id, step.action, step.target or "", step.value or "")

    def _add_step_row(self) -> None:
        step_num = self._steps_table.rowCount() + 1
        self._insert_step_row(f"step_{step_num}", "click", "", "")
        self._renumber_steps()

    def _insert_step_after_selection(self) -> None:
        """Insert a new step row after the currently selected row.

        If no row is selected, appends at the end (same as _add_step_row).
        """
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
        """Insert a step row at a specific position and rebind all button signals."""
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, QTableWidgetItem(step_id))

        action_combo = QComboBox()
        action_combo.setMinimumHeight(28)
        for act_key, act_label in _ACTION_NOTES.items():
            action_combo.addItem(f"{act_key} · {act_label}", act_key)
        idx = action_combo.findData(action)
        if idx >= 0:
            action_combo.setCurrentIndex(idx)
        self._steps_table.setCellWidget(row, 1, action_combo)

        self._steps_table.setItem(row, 2, QTableWidgetItem(target))
        self._steps_table.setItem(row, 3, QTableWidgetItem(str(value)))

        # Up/Down buttons
        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setContentsMargins(2, 2, 2, 2)
        move_layout.setSpacing(4)
        up_btn = QPushButton("↑")
        up_btn.setObjectName("Ghost")
        up_btn.setMaximumWidth(32)
        up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
        down_btn = QPushButton("↓")
        down_btn.setObjectName("Ghost")
        down_btn.setMaximumWidth(32)
        down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
        move_layout.addWidget(up_btn)
        move_layout.addWidget(down_btn)
        self._steps_table.setCellWidget(row, 4, move_widget)

        delete = QPushButton("删除")
        delete.setObjectName("Danger")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
        self._steps_table.setCellWidget(row, 5, delete)

        # Rebind all row buttons so lambda closures point to the correct indices.
        self._rebind_step_buttons()

    def _insert_step_row(self, step_id: str, action: str, target: str, value: str) -> None:
        row = self._steps_table.rowCount()
        self._steps_table.insertRow(row)
        self._steps_table.setItem(row, 0, QTableWidgetItem(step_id))

        action_combo = QComboBox()
        action_combo.setMinimumHeight(28)
        for act_key, act_label in _ACTION_NOTES.items():
            action_combo.addItem(f"{act_key} · {act_label}", act_key)
        idx = action_combo.findData(action)
        if idx >= 0:
            action_combo.setCurrentIndex(idx)
        self._steps_table.setCellWidget(row, 1, action_combo)

        self._steps_table.setItem(row, 2, QTableWidgetItem(target))
        self._steps_table.setItem(row, 3, QTableWidgetItem(str(value)))

        # Up/Down buttons
        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setContentsMargins(2, 2, 2, 2)
        move_layout.setSpacing(4)
        up_btn = QPushButton("↑")
        up_btn.setObjectName("Ghost")
        up_btn.setMaximumWidth(32)
        up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
        down_btn = QPushButton("↓")
        down_btn.setObjectName("Ghost")
        down_btn.setMaximumWidth(32)
        down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
        move_layout.addWidget(up_btn)
        move_layout.addWidget(down_btn)
        self._steps_table.setCellWidget(row, 4, move_widget)

        delete = QPushButton("删除")
        delete.setObjectName("Danger")
        delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
        self._steps_table.setCellWidget(row, 5, delete)

    def _delete_step_row(self, row: int) -> None:
        self._steps_table.removeRow(row)
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
        # Collect data from both rows
        data1 = self._collect_step_row_data(row1)
        data2 = self._collect_step_row_data(row2)
        # Swap
        self._set_step_row_data(row1, data2)
        self._set_step_row_data(row2, data1)
        self._renumber_steps()

    def _renumber_steps(self) -> None:
        """Renumber all step IDs as step_1..step_N based on current row order."""
        for row in range(self._steps_table.rowCount()):
            item = self._steps_table.item(row, 0)
            if item is not None:
                item.setText(f"step_{row + 1}")

    def _collect_step_row_data(self, row: int) -> tuple:
        step_id = self._table_text(self._steps_table, row, 0)
        action_combo = self._steps_table.cellWidget(row, 1)
        action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
        target = self._table_text(self._steps_table, row, 2)
        value = self._table_text(self._steps_table, row, 3)
        return (step_id, action, target, value)

    def _set_step_row_data(self, row: int, data: tuple) -> None:
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
            # Rebind move buttons
            move_widget = QWidget()
            move_layout = QHBoxLayout(move_widget)
            move_layout.setContentsMargins(2, 2, 2, 2)
            move_layout.setSpacing(4)
            up_btn = QPushButton("↑")
            up_btn.setObjectName("Ghost")
            up_btn.setMaximumWidth(32)
            up_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_up(r))
            down_btn = QPushButton("↓")
            down_btn.setObjectName("Ghost")
            down_btn.setMaximumWidth(32)
            down_btn.clicked.connect(lambda _checked=False, r=row: self._move_step_down(r))
            move_layout.addWidget(up_btn)
            move_layout.addWidget(down_btn)
            self._steps_table.setCellWidget(row, 4, move_widget)

            # Rebind delete button
            delete = QPushButton("删除")
            delete.setObjectName("Danger")
            delete.clicked.connect(lambda _checked=False, r=row: self._delete_step_row(r))
            self._steps_table.setCellWidget(row, 5, delete)

    def _collect_steps(self) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []
        for row in range(self._steps_table.rowCount()):
            step_id = self._table_text(self._steps_table, row, 0)
            action_combo = self._steps_table.cellWidget(row, 1)
            action = action_combo.currentData() if isinstance(action_combo, QComboBox) else "click"
            target = self._table_text(self._steps_table, row, 2) or None
            value_text = self._table_text(self._steps_table, row, 3)
            value = value_text if value_text else None

            if not step_id:
                raise ValueError("步骤 ID 不能为空")
            if not action:
                raise ValueError(f"步骤 {step_id} 未选择动作")

            steps.append(WorkflowStep(id=step_id, action=action, target=target, value=value))
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
        delete = QPushButton("删除")
        delete.setObjectName("Danger")
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
        existing = {self._table_text(self._binding_table, row, 0) for row in range(self._binding_table.rowCount())}
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
        delete = QPushButton("删除")
        delete.setObjectName("Danger")
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
        existing = {self._table_text(self._output_table, row, 0) for row in range(self._output_table.rowCount())}
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
            button = QPushButton("删除")
            button.setObjectName("Danger")
            button.clicked.connect(lambda _checked=False, r=row: handler(r))
            table.setCellWidget(row, 2, button)

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
            f"<span style='color:{t.SUCCESS};font-weight:600;'>已保存工作流配置。</span>"
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
                f"<span style='color:{t.SUCCESS};font-weight:600;'>✓ 通过标准化检查，"
                "可进入 Standardized。</span>"
            )
            return
        rows = [f"<div style='color:{t.DANGER};font-weight:600;'>✕ 未通过，需修复：</div>"]
        for issue in result.issues:
            rows.append(f"<div style='color:{t.INK_MUTED};margin:3px 0;'>· {issue}</div>")
        self._precheck.setText("".join(rows))
