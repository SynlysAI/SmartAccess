"""工作流设计页面。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QInputDialog,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from smartaccess_v2.desktop.viewmodels.workflow_vm import WorkflowViewModel


def _selectable_msg(parent, icon, title, text):
    """创建可选中文本的消息弹窗。"""

    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, parent)
    for label in box.findChildren(QLabel):
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return box
from smartaccess_v2.desktop.widgets.background_worker import BackgroundTask
from smartaccess_v2.desktop.widgets.cards import create_card
from smartaccess_v2.desktop.widgets.table_style import NoWheelComboBox
from smartaccess_v2.desktop.widgets.workflow_step_table import StepRow, WorkflowStepTable
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)


class WorkflowPage(QWidget):
    """工作流列表、步骤编辑和标准化检查页面。"""

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化工作流页面。"""

        super().__init__(parent)
        self._vm = WorkflowViewModel(facade, self)
        self._current: WorkflowContract | None = None
        self._anchor_ids: list[str] = []
        self._last_ai_prompt = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 740])
        root.addWidget(splitter, 1)
        self._reload_profiles()
        self._reload_workflows()

    def on_show(self) -> None:
        """页面显示时刷新列表。"""

        self._reload_profiles()
        self._reload_workflows()

    def _build_header(self) -> QHBoxLayout:
        """构建顶部按钮区。"""

        row = QHBoxLayout()
        title = QLabel("工作流设计")
        title.setObjectName("PageTitle")
        row.addWidget(title)
        row.addStretch(1)
        new_btn = QPushButton("新建")
        new_btn.setObjectName("Secondary")
        new_btn.clicked.connect(self._new_workflow)
        row.addWidget(new_btn)
        check_btn = QPushButton("检查")
        check_btn.setObjectName("Secondary")
        check_btn.clicked.connect(self._standardize)
        row.addWidget(check_btn)
        self._ai_btn = QPushButton("AI生成")
        self._ai_btn.setObjectName("Secondary")
        self._ai_btn.clicked.connect(self._ai_generate)
        row.addWidget(self._ai_btn)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return row

    def _build_left_panel(self) -> QWidget:
        """构建左侧工作流列表。"""

        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(240)
        label = QLabel("工作流")
        label.setObjectName("PageHint")
        layout.addWidget(label)
        self._workflow_list = QListWidget()
        self._workflow_list.itemSelectionChanged.connect(self._select_workflow)
        self._workflow_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._workflow_list.customContextMenuRequested.connect(self._workflow_menu)
        layout.addWidget(self._workflow_list, 1)
        return panel

    def _build_editor(self) -> QWidget:
        """构建右侧步骤编辑区。"""

        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=12)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        form = QFormLayout()
        self._workflow_id = QLineEdit()
        self._workflow_id.setPlaceholderText("wf_new_experiment")
        self._anchor_profile = NoWheelComboBox()
        self._anchor_profile.currentIndexChanged.connect(self._on_profile_changed)
        self._author = QLineEdit("smartaccess")
        self._lifecycle = NoWheelComboBox()
        for state in ("Draft", "Standardized", "Published"):
            self._lifecycle.addItem(state, state)
        self._template_id = QLineEdit()
        self._template_version = QLineEdit()
        form.addRow("工作流 ID", self._workflow_id)
        form.addRow("设备", self._anchor_profile)
        form.addRow("作者", self._author)
        form.addRow("状态", self._lifecycle)
        form.addRow("模板 ID", self._template_id)
        form.addRow("模板版本", self._template_version)
        layout.addLayout(form)

        layout.addLayout(self._build_step_toolbar())
        self._steps = WorkflowStepTable()
        self._steps.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self._steps)
        layout.addWidget(self._build_result_box())
        return panel

    def _build_step_toolbar(self) -> QHBoxLayout:
        """构建步骤表局部操作栏。

        Returns:
            步骤表局部操作按钮布局。
        """

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel("步骤")
        label.setObjectName("PageHint")
        row.addWidget(label)
        row.addStretch(1)
        add_action_btn = QPushButton("添加动作")
        add_action_btn.setObjectName("TableToolbarButton")
        add_action_btn.clicked.connect(self._add_action)
        row.addWidget(add_action_btn)
        insert_action_btn = QPushButton("插入动作")
        insert_action_btn.setObjectName("TableToolbarButton")
        insert_action_btn.clicked.connect(self._insert_action)
        row.addWidget(insert_action_btn)
        wait_btn = QPushButton("插入等待")
        wait_btn.setObjectName("TableToolbarButton")
        wait_btn.clicked.connect(self._insert_wait)
        row.addWidget(wait_btn)
        return row

    def _build_result_box(self) -> QWidget:
        """构建检查和 AI 生成结果展示区。

        Returns:
            位于步骤表下方的独立结果区域。
        """

        panel = QWidget()
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        label = QLabel("信息")
        label.setObjectName("PageHint")
        layout.addWidget(label)

        self._result = QPlainTextEdit()
        self._result.setObjectName("WorkflowResult")
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("检查或 AI 生成结果会显示在这里。")
        self._result.setMinimumHeight(50)
        self._result.setMaximumHeight(120)
        self._result.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self._result)
        return panel

    def _reload_profiles(self) -> None:
        """刷新设备下拉框。"""

        current = self._anchor_profile.currentData()
        self._anchor_profile.blockSignals(True)
        self._anchor_profile.clear()
        for profile in self._vm.list_anchor_profiles():
            self._anchor_profile.addItem(profile.profile_id, profile.profile_id)
        index = self._anchor_profile.findData(current)
        if index >= 0:
            self._anchor_profile.setCurrentIndex(index)
        self._anchor_profile.blockSignals(False)
        self._on_profile_changed()

    def _reload_workflows(self, selected_workflow_id: str | None = None) -> None:
        """刷新工作流列表。

        Args:
            selected_workflow_id: 刷新后需要保留选中的工作流 ID。
        """

        current_id = selected_workflow_id
        if current_id is None and self._current is not None:
            current_id = self._current.metadata.workflow_id
        self._workflow_list.blockSignals(True)
        self._workflow_list.clear()
        selected_item: QListWidgetItem | None = None
        for workflow in self._vm.list_workflows():
            item = QListWidgetItem(workflow.metadata.workflow_id)
            item.setData(Qt.ItemDataRole.UserRole, workflow.metadata.workflow_id)
            self._workflow_list.addItem(item)
            if workflow.metadata.workflow_id == current_id:
                selected_item = item
        if self._workflow_list.count() == 0:
            self._workflow_list.addItem("暂无工作流")
        elif selected_item is not None:
            self._workflow_list.setCurrentItem(selected_item)
        self._workflow_list.blockSignals(False)

    def _on_profile_changed(self) -> None:
        """设备变化时刷新锚点列表。"""

        profile = self._vm.get_anchor_profile(self._anchor_profile.currentData())
        self._anchor_ids = [anchor.id for anchor in profile.anchors] if profile else []
        if hasattr(self, "_steps"):
            self._steps.set_steps(self._steps.rows(), self._anchor_ids)

    def _new_workflow(self) -> None:
        """创建空工作流编辑状态。"""

        self._current = None
        self._workflow_id.setText(self._next_workflow_id())
        self._author.setText("smartaccess")
        self._lifecycle.setCurrentIndex(0)
        self._template_id.clear()
        self._template_version.clear()
        self._steps.set_steps([], self._anchor_ids)
        self._clear_result()

    def _select_workflow(self) -> None:
        """列表选择工作流后加载编辑。"""

        item = self._workflow_list.currentItem()
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        if not workflow_id:
            return
        workflow = next(
            (
                item
                for item in self._vm.list_workflows()
                if item.metadata.workflow_id == workflow_id
            ),
            None,
        )
        if workflow is not None:
            self._load_workflow(workflow)

    def _load_workflow(self, workflow: WorkflowContract) -> None:
        """加载工作流到编辑器。"""

        self._current = workflow
        meta = workflow.metadata
        self._workflow_id.setText(meta.workflow_id)
        index = self._anchor_profile.findData(meta.anchor_profile)
        if index >= 0:
            self._anchor_profile.setCurrentIndex(index)
        self._author.setText(meta.author)
        state_index = self._lifecycle.findData(meta.lifecycle_state)
        self._lifecycle.setCurrentIndex(max(0, state_index))
        self._template_id.setText(meta.template_id or "")
        self._template_version.setText(meta.template_version or "")
        rows = [
            StepRow(
                step_id=step.id,
                action=step.action,
                anchor_id=step.anchor_id,
                value=step.value,
                wait_seconds=step.wait_seconds,
                match_mode=step.match_mode,
                expected_text=step.expected_text,
                timeout_seconds=step.timeout_seconds,
                requires_confirmation=step.requires_confirmation,
            )
            for step in workflow.steps
        ]
        self._steps.set_steps(rows, self._anchor_ids)
        self._clear_result()

    def _add_action(self) -> None:
        """在步骤末尾添加普通动作。"""

        self._steps.insert_action(self._steps.rowCount())

    def _insert_action(self) -> None:
        """在当前选择行之后插入普通动作。"""

        row = self._steps.currentRow()
        insert_at = self._steps.rowCount() if row < 0 else row + 1
        self._steps.insert_action(insert_at)

    def _insert_wait(self) -> None:
        """在当前选择行之后插入等待步骤。"""

        row = self._steps.currentRow()
        insert_at = self._steps.rowCount() if row < 0 else row + 1
        self._steps.insert_wait(insert_at)

    def _save(self) -> None:
        """保存当前工作流。"""

        try:
            workflow = self._build_workflow()
            saved = self._vm.save_workflow(workflow)
        except Exception as exc:  # noqa: BLE001
            _selectable_msg(self, QMessageBox.Icon.Critical, "保存失败", str(exc)).exec()
            return
        self._current = saved
        self._reload_workflows()
        self._set_result(f"已保存：{saved.metadata.workflow_id}")

    def _standardize(self) -> None:
        """执行标准化检查。"""

        try:
            workflow = self._build_workflow()
            result = self._vm.standardize(workflow)
        except Exception as exc:  # noqa: BLE001
            _selectable_msg(self, QMessageBox.Icon.Critical, "检查失败", str(exc)).exec()
            return
        if result.ok:
            self._set_result("标准化检查通过")
        else:
            self._set_result("\n".join(result.issues))

    def _ai_generate(self) -> None:
        """根据文本描述调用 AI 生成工作流。"""

        prompt, ok = QInputDialog.getMultiLineText(
            self,
            "AI生成工作流",
            (
                "输入实验步骤或自动化目标。\n"
                f"当前 AI：{self._vm.ai_label()}"
            ),
            self._last_ai_prompt,
        )
        if not ok:
            return
        prompt = prompt.strip()
        if not prompt:
            _selectable_msg(self, QMessageBox.Icon.Warning, "缺少描述", "请输入实验步骤或自动化目标。").exec()
            return
        self._last_ai_prompt = prompt
        workflow_id = self._workflow_id.text().strip() or self._next_workflow_id()
        anchor_profile = self._anchor_profile.currentData()
        if not anchor_profile:
            _selectable_msg(self, QMessageBox.Icon.Warning, "缺少设备", "请先选择设备。").exec()
            return
        profile = self._vm.get_anchor_profile(str(anchor_profile))
        anchors = []
        if profile is not None:
            anchors = [
                {
                    "id": anchor.id,
                    "supported_actions": list(anchor.supported_actions),
                    "has_ocr": anchor.observe_region is not None,
                    "default_wait_seconds": anchor.default_wait_seconds,
                }
                for anchor in profile.anchors
            ]
        context = {
            "workflow_id": workflow_id,
            "anchor_profile": str(anchor_profile),
            "experiment_type": "generic_automation",
            "anchors": anchors,
            "available_actions": sorted(
                {action for item in anchors for action in item["supported_actions"]}
            ),
        }

        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("生成中...")
        self._set_result("AI 生成中，请稍候...")

        self._ai_task = BackgroundTask(
            lambda: self._vm.draft_workflow(prompt, context), parent=self
        )
        self._ai_task.done.connect(self._on_ai_generate_done)
        self._ai_task.error.connect(self._on_ai_generate_error)
        self._ai_task.start()

    def _on_ai_generate_done(self, result: object) -> None:
        """AI 生成工作流完成后的回调。"""

        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI生成")
        self._load_workflow(result)
        self._reload_workflows(result.metadata.workflow_id)
        self._steps.scrollToTop()
        self._set_result(self._vm.ai_reasoning() or "AI 工作流已生成")

    def _on_ai_generate_error(self, msg: str) -> None:
        """AI 生成工作流失败后的回调。"""

        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI生成")
        self._clear_result()
        _selectable_msg(self, QMessageBox.Icon.Critical, "AI生成失败", msg).exec()

    def _build_workflow(self) -> WorkflowContract:
        """从编辑器构建工作流契约。"""

        workflow_id = self._workflow_id.text().strip()
        anchor_profile = self._anchor_profile.currentData()
        if not workflow_id:
            raise ValueError("请输入工作流 ID")
        if not anchor_profile:
            raise ValueError("请选择设备")
        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            anchor_profile=str(anchor_profile),
            author=self._author.text().strip() or "smartaccess",
            lifecycle_state=str(self._lifecycle.currentData() or "Draft"),
            template_id=self._template_id.text().strip() or None,
            template_version=self._template_version.text().strip() or None,
        )
        steps = []
        for row in self._steps.rows():
            payload = {
                "id": row.step_id,
                "action": row.action,
                "anchor_id": row.anchor_id,
                "value": row.value,
                "wait_seconds": row.wait_seconds,
                "match_mode": row.match_mode,
                "expected_text": row.expected_text,
                "timeout_seconds": row.timeout_seconds,
                "requires_confirmation": row.requires_confirmation,
            }
            steps.append(WorkflowStep.model_validate(payload))
        return WorkflowContract(metadata=metadata, steps=steps)

    def _workflow_menu(self, pos) -> None:
        """显示工作流右键菜单。"""

        item = self._workflow_list.itemAt(pos)
        if item is None:
            return
        workflow_id = item.data(Qt.ItemDataRole.UserRole)
        if not workflow_id:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除")
        if menu.exec(self._workflow_list.mapToGlobal(pos)) == delete_action:
            self._delete_workflow(str(workflow_id))

    def _delete_workflow(self, workflow_id: str) -> None:
        """删除工作流。"""

        reply = QMessageBox.question(
            self,
            "删除工作流",
            f"确认删除 {workflow_id}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._vm.delete_workflow(workflow_id)
        self._current = None
        self._reload_workflows()

    def _next_workflow_id(self) -> str:
        """生成工作流 ID。"""

        existing = {workflow.metadata.workflow_id for workflow in self._vm.list_workflows()}
        index = 1
        while f"workflow_{index}" in existing:
            index += 1
        return f"workflow_{index}"

    def _set_result(self, message: str) -> None:
        """设置步骤区状态提示。

        Args:
            message: 完整状态文本。
        """

        text = message.strip()
        self._result.setPlainText(text)
        self._result.setToolTip(text)

    def _clear_result(self) -> None:
        """清空步骤区状态提示。"""

        self._result.clear()
        self._result.setToolTip("")
