"""工作流设计页面。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from smartaccess_v2.desktop.viewmodels.workflow_vm import WorkflowViewModel
from smartaccess_v2.desktop.widgets.cards import create_card
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

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 920])
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
        add_action_btn = QPushButton("添加动作")
        add_action_btn.setObjectName("Secondary")
        add_action_btn.clicked.connect(self._add_action)
        row.addWidget(add_action_btn)
        insert_action_btn = QPushButton("插入动作")
        insert_action_btn.setObjectName("Secondary")
        insert_action_btn.clicked.connect(self._insert_action)
        row.addWidget(insert_action_btn)
        wait_btn = QPushButton("插入等待")
        wait_btn.setObjectName("Secondary")
        wait_btn.clicked.connect(self._insert_wait)
        row.addWidget(wait_btn)
        check_btn = QPushButton("检查")
        check_btn.setObjectName("Secondary")
        check_btn.clicked.connect(self._standardize)
        row.addWidget(check_btn)
        ai_btn = QPushButton("AI生成")
        ai_btn.setObjectName("Secondary")
        ai_btn.clicked.connect(self._ai_generate)
        row.addWidget(ai_btn)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return row

    def _build_left_panel(self) -> QWidget:
        """构建左侧工作流列表。"""

        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(310)
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

        form = QFormLayout()
        self._workflow_id = QLineEdit()
        self._workflow_id.setPlaceholderText("wf_new_experiment")
        self._anchor_profile = QComboBox()
        self._anchor_profile.currentIndexChanged.connect(self._on_profile_changed)
        self._author = QLineEdit("smartaccess")
        self._lifecycle = QComboBox()
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

        self._ai_prompt = QTextEdit()
        self._ai_prompt.setObjectName("PromptEditor")
        self._ai_prompt.setPlaceholderText("输入实验步骤或自动化目标，点击 AI生成")
        self._ai_prompt.setMaximumHeight(92)
        layout.addWidget(self._ai_prompt)

        self._steps = WorkflowStepTable()
        layout.addWidget(self._steps, 1)
        self._result = QTextEdit()
        self._result.setObjectName("ResultEditor")
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(120)
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

    def _reload_workflows(self) -> None:
        """刷新工作流列表。"""

        current_id = self._current.metadata.workflow_id if self._current else None
        self._workflow_list.clear()
        for workflow in self._vm.list_workflows():
            item = QListWidgetItem(workflow.metadata.workflow_id)
            item.setData(Qt.ItemDataRole.UserRole, workflow.metadata.workflow_id)
            self._workflow_list.addItem(item)
            if workflow.metadata.workflow_id == current_id:
                self._workflow_list.setCurrentItem(item)
        if self._workflow_list.count() == 0:
            self._workflow_list.addItem("暂无工作流")

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
        self._result.clear()

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
        self._result.clear()

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
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._current = saved
        self._reload_workflows()
        self._result.setPlainText(f"已保存：{saved.metadata.workflow_id}")

    def _standardize(self) -> None:
        """执行标准化检查。"""

        try:
            workflow = self._build_workflow()
            result = self._vm.standardize(workflow)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "检查失败", str(exc))
            return
        if result.ok:
            self._result.setPlainText("标准化检查通过")
        else:
            self._result.setPlainText("\n".join(result.issues))

    def _ai_generate(self) -> None:
        """根据文本描述调用 AI 生成工作流。"""

        prompt = self._ai_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "缺少描述", "请输入实验步骤或自动化目标。")
            return
        workflow_id = self._workflow_id.text().strip() or self._next_workflow_id()
        anchor_profile = self._anchor_profile.currentData()
        if not anchor_profile:
            QMessageBox.warning(self, "缺少设备", "请先选择设备。")
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
        try:
            workflow = self._vm.draft_workflow(prompt, context)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "AI生成失败", str(exc))
            return
        self._load_workflow(workflow)
        self._reload_workflows()
        self._result.setPlainText(self._vm.ai_reasoning() or "AI 工作流已生成")

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
