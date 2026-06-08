"""Workflow design page: AI draft, step orchestration, standardization check."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.viewmodels.workflow_vm import WorkflowViewModel
from smartaccess.desktop.widgets.cards import Card, page_header, section_title
from smartaccess.shared.contracts.workflow import WorkflowContract


class WorkflowPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = WorkflowViewModel(facade, self)
        self._current: WorkflowContract | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("工作流设计", "AI 生成、锚点绑定、步骤编排、预检与标准化"))

        body = QHBoxLayout()
        body.setSpacing(16)

        left = Card()
        left.add(section_title("AI 生成工作流"))
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("用自然语言描述实验步骤……")
        self._prompt.setPlainText("打开方法编辑器，设定目标参数，启动运行并等待状态变化。")
        left.add(self._prompt)
        self._workflow_id = QLineEdit("wf_new_experiment")
        left.add(self._workflow_id)
        self._device = QComboBox()
        left.add(self._device)
        generate = QPushButton("生成草稿")
        generate.clicked.connect(self._generate)
        left.add(generate)
        left.add(section_title("已有工作流"))
        self._workflows = QListWidget()
        self._workflows.itemSelectionChanged.connect(self._select_existing)
        left.add(self._workflows)

        right = Card()
        tabs = QTabWidget()
        steps_tab = QWidget()
        steps_layout = QVBoxLayout(steps_tab)
        self._steps = QListWidget()
        steps_layout.addWidget(self._steps)
        bindings_tab = QWidget()
        bindings_layout = QVBoxLayout(bindings_tab)
        self._bindings = QListWidget()
        bindings_layout.addWidget(self._bindings)
        precheck_tab = QWidget()
        precheck_layout = QVBoxLayout(precheck_tab)
        self._precheck = QListWidget()
        precheck_layout.addWidget(self._precheck)
        check = QPushButton("运行标准化检查")
        check.setObjectName("Ghost")
        check.clicked.connect(self._standardize)
        precheck_layout.addWidget(check)
        tabs.addTab(steps_tab, "步骤")
        tabs.addTab(bindings_tab, "锚点")
        tabs.addTab(precheck_tab, "预检")
        right.add(tabs)

        body.addWidget(left, 2)
        body.addWidget(right, 3)
        root.addLayout(body, 1)

        self._reload()

    def _reload(self) -> None:
        self._device.clear()
        self._device.addItems(self._vm.list_instrument_ids() or ["unknown_device"])
        self._workflows.clear()
        for wf in self._vm.list_workflows():
            self._workflows.addItem(f"{wf.metadata.workflow_id}  ·  {wf.metadata.lifecycle_state}")

    def _generate(self) -> None:
        try:
            workflow = self._vm.generate(
                self._prompt.toPlainText(),
                device_id=self._device.currentText() or None,
                workflow_id=self._workflow_id.text().strip() or "wf_new_experiment",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "生成失败", str(exc))
            return
        self._show_workflow(workflow)
        self._reload()

    def _select_existing(self) -> None:
        idx = self._workflows.currentRow()
        workflows = self._vm.list_workflows()
        if 0 <= idx < len(workflows):
            self._show_workflow(workflows[idx])

    def _show_workflow(self, workflow: WorkflowContract) -> None:
        self._current = workflow
        self._steps.clear()
        for step in workflow.steps:
            target = f" -> {step.target}" if step.target else ""
            value = f" = {step.value}" if step.value is not None else ""
            self._steps.addItem(f"{step.id}: {step.action}{target}{value}")
        self._bindings.clear()
        for key, roi in workflow.roi_bindings.items():
            self._bindings.addItem(f"{key} -> {roi}")
        if not workflow.roi_bindings:
            self._bindings.addItem("无 ROI 绑定")
        self._precheck.clear()

    def _standardize(self) -> None:
        if self._current is None:
            self._precheck.clear()
            self._precheck.addItem("请先生成或选择一个工作流")
            return
        result = self._vm.standardize(self._current)
        self._precheck.clear()
        if result.ok:
            self._precheck.addItem("通过标准化检查，可进入 Standardized")
        else:
            for issue in result.issues:
                self._precheck.addItem(f"{issue}")
