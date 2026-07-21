"""SmartDataHub 数据采集配置与运行监控页面。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess.data_collection.config import (
    CollectionConfig,
    DATA_TYPE_OPTIONS,
    WatcherConfig,
)
from smartaccess.data_collection.controller import CollectionRuntimeStatus
from smartaccess.desktop.viewmodels.data_collection_vm import DataCollectionViewModel
from smartaccess.desktop.widgets.background_worker import BackgroundTask
from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.table_style import configure_data_table
from smartaccess.runtime.application.facade import RuntimeFacade


class DataCollectionPage(QWidget):
    """配置并管理内嵌 SmartDataHub 数据采集器。"""

    WATCHER_HEADERS = (
        "名称",
        "类型",
        "监听路径",
        "匹配模式",
        "数据类型",
        "递归",
        "更新采集",
    )
    STATUS_HEADERS = ("监听器", "监听路径", "状态")

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化数据采集页面。

        Args:
            facade: SmartAccess 运行时门面。
            parent: 可选 Qt 父对象。
        """

        super().__init__(parent)
        self._vm = DataCollectionViewModel(facade, self)
        self._watchers: list[WatcherConfig] = []
        self._task: BackgroundTask | None = None
        self._config_loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        config_card, config_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        config_layout.addLayout(self._build_config_form())
        content_layout.addWidget(config_card)

        watcher_card, watcher_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        watcher_layout.addLayout(self._build_watcher_section())
        content_layout.addWidget(watcher_card)

        status_card, status_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        status_layout.addLayout(self._build_status_section())
        content_layout.addWidget(status_card)
        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        root.addWidget(scroll_area, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()
        self._load_configuration()
        self._refresh_status()

    def on_show(self) -> None:
        """页面显示时刷新采集器状态。"""

        if not self._config_loaded and not self._vm.is_running():
            self._load_configuration()
        self._refresh_status()

    def shutdown(self) -> None:
        """主窗口关闭时安全停止数据采集器。"""

        self._timer.stop()
        if self._vm.is_running():
            self._vm.stop()

    def _build_header(self) -> QHBoxLayout:
        """构建页面标题和启动控制区。

        Returns:
            页面顶部布局。
        """

        row = QHBoxLayout()
        title = QLabel("数据采集")
        title.setObjectName("PageTitle")
        row.addWidget(title)
        row.addWidget(QLabel("将本地设备数据可靠上传至 SmartDataHub"))
        row.addStretch(1)
        self._state_label = QLabel("未启动")
        self._state_label.setObjectName("PageHint")
        row.addWidget(self._state_label)
        self._save_button = QPushButton("保存配置")
        self._save_button.setObjectName("Secondary")
        self._save_button.clicked.connect(self._save_configuration)
        row.addWidget(self._save_button)
        self._start_button = QPushButton("启动采集")
        self._start_button.clicked.connect(self._start_collection)
        row.addWidget(self._start_button)
        self._stop_button = QPushButton("停止采集")
        self._stop_button.setObjectName("Danger")
        self._stop_button.clicked.connect(self._stop_collection)
        row.addWidget(self._stop_button)
        return row

    def _build_config_form(self) -> QFormLayout:
        """构建采集器与中心服务配置表单。

        Returns:
            配置表单布局。
        """

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._collector_id = QLineEdit()
        self._collector_id.setPlaceholderText("例如 nmr_pc_01")
        self._site = QLineEdit()
        self._site.setPlaceholderText("例如 Lab-A")
        self._timeout = self._create_spin_box(1, 3600, 30, "秒")
        self._retry_interval = self._create_spin_box(1, 3600, 30, "秒")
        self._upload_existing = QCheckBox("启动时扫描当前已存在的数据")
        self._upload_existing.setChecked(True)
        self._force_upload_existing = QCheckBox("强制重新上传已扫描过的数据")
        self._force_upload_existing.setEnabled(True)
        self._upload_existing.toggled.connect(self._force_upload_existing.setEnabled)

        form.addRow("采集器 ID", self._collector_id)
        form.addRow("站点", self._site)
        form.addRow("请求超时", self._timeout)
        form.addRow("失败重试间隔", self._retry_interval)
        form.addRow("历史数据", self._upload_existing)
        form.addRow("重复历史数据", self._force_upload_existing)
        return form

    def _build_watcher_section(self) -> QVBoxLayout:
        """构建监听器配置表格和编辑操作。

        Returns:
            监听器区域布局。
        """

        layout = QVBoxLayout()
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("监听器配置"))
        toolbar.addStretch(1)
        add_button = QPushButton("添加监听器")
        add_button.clicked.connect(self._add_watcher)
        toolbar.addWidget(add_button)
        edit_button = QPushButton("编辑")
        edit_button.setObjectName("Secondary")
        edit_button.clicked.connect(self._edit_watcher)
        toolbar.addWidget(edit_button)
        delete_button = QPushButton("删除")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete_watcher)
        toolbar.addWidget(delete_button)
        layout.addLayout(toolbar)

        self._watcher_table = QTableWidget(0, len(self.WATCHER_HEADERS))
        self._watcher_table.setHorizontalHeaderLabels(self.WATCHER_HEADERS)
        configure_data_table(self._watcher_table, row_height=36, stretch_last=True)
        self._watcher_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._watcher_table.setColumnWidth(2, 300)
        self._watcher_table.setColumnWidth(3, 180)
        layout.addWidget(self._watcher_table)
        return layout

    def _build_status_section(self) -> QVBoxLayout:
        """构建采集运行状态与队列监控区域。

        Returns:
            状态区域布局。
        """

        layout = QVBoxLayout()
        self._summary_label = QLabel()
        self._summary_label.setObjectName("PageHint")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)
        self._status_table = QTableWidget(0, len(self.STATUS_HEADERS))
        self._status_table.setHorizontalHeaderLabels(self.STATUS_HEADERS)
        configure_data_table(self._status_table, row_height=34, stretch_last=True)
        self._status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._status_table)
        return layout

    def _load_configuration(self) -> None:
        """将工作区采集配置回填到页面表单。"""

        try:
            config = self._vm.load_configuration()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "加载采集配置失败", str(exc))
            return
        self._fill_configuration(config)
        self._config_loaded = True

    def _fill_configuration(self, config: CollectionConfig) -> None:
        """将采集配置写入各个页面控件。

        Args:
            config: 待展示的数据采集配置。
        """

        self._collector_id.setText(config.collector.collector_id)
        self._site.setText(config.collector.site)
        self._timeout.setValue(config.server.timeout_seconds)
        self._retry_interval.setValue(config.queue.retry_interval_seconds)
        self._watchers = list(config.watchers)
        self._refresh_watcher_table()

    def _collect_configuration(self) -> CollectionConfig:
        """从页面控件读取并构造完整采集配置。

        Returns:
            数据采集配置对象。
        """

        return self._vm.build_configuration(
            collector_id=self._collector_id.text().strip(),
            site=self._site.text().strip(),
            timeout_seconds=self._timeout.value(),
            retry_interval_seconds=self._retry_interval.value(),
            watchers=self._watchers,
        )

    def _save_configuration(self) -> None:
        """保存当前页面填写的数据采集配置。"""

        try:
            path = self._vm.save_configuration(self._collect_configuration())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存配置失败", str(exc))
            return
        self._state_label.setText(f"配置已保存: {path}")

    def _start_collection(self) -> None:
        """在后台线程保存配置并启动采集器。"""

        if self._task is not None and self._task.isRunning():
            return
        try:
            config = self._collect_configuration()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "读取配置失败", str(exc))
            return
        self._set_actions_enabled(False)
        self._state_label.setText("正在启动采集器…")
        self._task = BackgroundTask(
            lambda: self._vm.start(
                config,
                upload_existing=self._upload_existing.isChecked(),
                force_upload_existing=self._force_upload_existing.isChecked(),
            ),
            self,
        )
        self._task.done.connect(self._on_operation_done)
        self._task.error.connect(self._on_operation_error)
        self._task.start()

    def _stop_collection(self) -> None:
        """在后台线程停止采集器。"""

        if self._task is not None and self._task.isRunning():
            return
        self._set_actions_enabled(False)
        self._state_label.setText("正在停止采集器…")
        self._task = BackgroundTask(self._vm.stop, self)
        self._task.done.connect(self._on_operation_done)
        self._task.error.connect(self._on_operation_error)
        self._task.start()

    def _on_operation_done(self, _result: object) -> None:
        """在后台启动或停止操作完成后刷新页面。"""

        self._set_actions_enabled(True)
        self._refresh_status()

    def _on_operation_error(self, message: str) -> None:
        """展示后台启动或停止操作的失败信息。

        Args:
            message: 后台任务错误文本。
        """

        self._set_actions_enabled(True)
        self._refresh_status()
        QMessageBox.warning(self, "数据采集操作失败", message)

    def _set_actions_enabled(self, enabled: bool) -> None:
        """设置启动、停止和保存按钮的可用状态。

        Args:
            enabled: 是否允许用户执行操作。
        """

        self._save_button.setEnabled(enabled)
        self._start_button.setEnabled(enabled and not self._vm.is_running())
        self._stop_button.setEnabled(enabled and self._vm.is_running())

    def _refresh_status(self) -> None:
        """刷新采集器运行状态、队列统计与监听器表格。"""

        status = self._vm.status()
        self._state_label.setText(_state_text(status.state, status.message))
        self._set_actions_enabled(self._task is None or not self._task.isRunning())
        self._summary_label.setText(_summary_text(status))
        self._status_table.setRowCount(len(status.watcher_states))
        for row_index, (name, path, is_running) in enumerate(status.watcher_states):
            values = (name, path, "监听中" if is_running else "已停止")
            for column_index, value in enumerate(values):
                self._status_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def _refresh_watcher_table(self) -> None:
        """刷新监听器配置表格。"""

        self._watcher_table.setRowCount(len(self._watchers))
        for row_index, watcher in enumerate(self._watchers):
            values = (
                watcher.name,
                "目录资产" if watcher.type == "directory" else "文件",
                str(watcher.path),
                ", ".join(watcher.patterns),
                DATA_TYPE_OPTIONS.get(watcher.data_type, "其它"),
                "是" if watcher.recursive else "否",
                "是" if watcher.watch_updates else "否",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, watcher)
                self._watcher_table.setItem(row_index, column_index, item)

    def _add_watcher(self) -> None:
        """打开新增监听器对话框。"""

        dialog = WatcherDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._watchers.append(dialog.watcher_config())
        self._refresh_watcher_table()

    def _edit_watcher(self) -> None:
        """编辑当前选中的监听器配置。"""

        row_index = self._watcher_table.currentRow()
        if row_index < 0:
            QMessageBox.information(self, "编辑监听器", "请先选择一个监听器")
            return
        dialog = WatcherDialog(self._watchers[row_index], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._watchers[row_index] = dialog.watcher_config()
        self._refresh_watcher_table()
        self._watcher_table.selectRow(row_index)

    def _delete_watcher(self) -> None:
        """删除当前选中的监听器配置。"""

        row_index = self._watcher_table.currentRow()
        if row_index < 0:
            QMessageBox.information(self, "删除监听器", "请先选择一个监听器")
            return
        name = self._watchers[row_index].name
        if QMessageBox.question(self, "删除监听器", f"确认删除监听器“{name}”吗？") != QMessageBox.StandardButton.Yes:
            return
        self._watchers.pop(row_index)
        self._refresh_watcher_table()

    @staticmethod
    def _create_spin_box(minimum: int, maximum: int, value: int, suffix: str) -> QSpinBox:
        """创建统一样式的整数输入框。

        Args:
            minimum: 最小值。
            maximum: 最大值。
            value: 默认值。
            suffix: 显示后缀。

        Returns:
            已配置的整数输入框。
        """

        spin_box = QSpinBox()
        spin_box.setRange(minimum, maximum)
        spin_box.setValue(value)
        spin_box.setSuffix(suffix)
        return spin_box


class WatcherDialog(QDialog):
    """新增或编辑单个数据采集监听器的对话框。"""

    def __init__(self, watcher: WatcherConfig | None = None, parent: QWidget | None = None) -> None:
        """初始化监听器编辑对话框。

        Args:
            watcher: 可选的现有监听器配置。
            parent: 可选 Qt 父对象。
        """

        super().__init__(parent)
        self.setWindowTitle("编辑监听器" if watcher else "添加监听器")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._type = QComboBox()
        self._type.addItem("文件", "file")
        self._type.addItem("目录资产", "directory")
        self._path = QLineEdit()
        browse_button = QPushButton("选择目录")
        browse_button.setObjectName("Secondary")
        browse_button.clicked.connect(self._choose_directory)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self._path, 1)
        path_layout.addWidget(browse_button)
        self._patterns = QLineEdit("*")
        self._data_type = QComboBox()
        for value, label in DATA_TYPE_OPTIONS.items():
            self._data_type.addItem(label, value)
        self._recursive = QCheckBox("递归监听子目录")
        self._recursive.setChecked(True)
        self._settle_seconds = DataCollectionPage._create_spin_box(0, 3600, 5, "秒")
        self._watch_updates = QCheckBox("采集文件后续修改")
        self._debounce_seconds = DataCollectionPage._create_spin_box(0, 3600, 30, "秒")
        form.addRow("名称", self._name)
        form.addRow("类型", self._type)
        form.addRow("监听目录", path_layout)
        form.addRow("匹配模式", self._patterns)
        form.addRow("数据类型", self._data_type)
        form.addRow("扫描方式", self._recursive)
        form.addRow("稳定等待", self._settle_seconds)
        form.addRow("更新采集", self._watch_updates)
        form.addRow("更新防抖", self._debounce_seconds)
        layout.addLayout(form)
        hint = QLabel("多个匹配模式用英文逗号分隔，例如：*.csv, *.json")
        hint.setObjectName("PageHint")
        layout.addWidget(hint)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("Secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        confirm_button = QPushButton("确定")
        confirm_button.clicked.connect(self._accept_if_valid)
        button_row.addWidget(confirm_button)
        layout.addLayout(button_row)
        if watcher is not None:
            self._fill_watcher(watcher)

    def watcher_config(self) -> WatcherConfig:
        """读取对话框中填写的监听器配置。

        Returns:
            用户填写的监听器配置。
        """

        patterns = [
            pattern.strip()
            for pattern in self._patterns.text().split(",")
            if pattern.strip()
        ]
        debounce = self._debounce_seconds.value()
        return WatcherConfig(
            name=self._name.text().strip(),
            type=str(self._type.currentData()),
            path=Path(self._path.text().strip()).expanduser(),
            patterns=patterns,
            recursive=self._recursive.isChecked(),
            data_type=str(self._data_type.currentData()),
            settle_seconds=self._settle_seconds.value(),
            watch_updates=self._watch_updates.isChecked(),
            update_debounce_seconds=debounce if debounce > 0 else None,
        )

    def _fill_watcher(self, watcher: WatcherConfig) -> None:
        """将现有监听器配置回填到对话框。

        Args:
            watcher: 待编辑的监听器配置。
        """

        self._name.setText(watcher.name)
        self._type.setCurrentIndex(0 if watcher.type == "file" else 1)
        self._path.setText(str(watcher.path))
        self._patterns.setText(", ".join(watcher.patterns))
        data_type_index = self._data_type.findData(watcher.data_type)
        self._data_type.setCurrentIndex(
            data_type_index if data_type_index >= 0 else self._data_type.findData("other")
        )
        self._recursive.setChecked(watcher.recursive)
        self._settle_seconds.setValue(watcher.settle_seconds)
        self._watch_updates.setChecked(watcher.watch_updates)
        self._debounce_seconds.setValue(watcher.update_debounce_seconds or 0)

    def _choose_directory(self) -> None:
        """选择监听目录并回填路径输入框。"""

        directory = QFileDialog.getExistingDirectory(self, "选择监听目录", self._path.text())
        if directory:
            self._path.setText(directory)

    def _accept_if_valid(self) -> None:
        """校验对话框必填字段后关闭对话框。"""

        watcher = self.watcher_config()
        if not watcher.name:
            QMessageBox.warning(self, "监听器配置", "请填写监听器名称")
            return
        if not self._path.text().strip():
            QMessageBox.warning(self, "监听器配置", "请选择监听目录")
            return
        if not watcher.patterns:
            QMessageBox.warning(self, "监听器配置", "请填写至少一个匹配模式")
            return
        self.accept()


def _state_text(state: str, message: str) -> str:
    """将内部状态转换为页面显示文本。

    Args:
        state: 内部运行状态。
        message: 附加状态说明。

    Returns:
        页面显示的状态文本。
    """

    labels = {
        "stopped": "已停止",
        "starting": "启动中",
        "running": "运行中",
        "stopping": "停止中",
        "error": "异常",
    }
    return f"{labels.get(state, state)} · {message}"


def _summary_text(status: CollectionRuntimeStatus) -> str:
    """构造上传队列与监听器状态摘要文本。

    Args:
        status: 采集器实时状态。

    Returns:
        页面展示的多行状态摘要。
    """

    started_at = (
        status.started_at.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(status.started_at, datetime)
        else "-"
    )
    queue_counts = status.queue_counts
    return (
        f"运行状态：{_state_text(status.state, status.message)}\n"
        f"启动时间：{started_at}    历史扫描入队：{status.initial_scan_files}\n"
        f"上传队列：待上传 {queue_counts.get('pending', 0)}，"
        f"已上传 {queue_counts.get('uploaded', 0)}，失败待重试 {queue_counts.get('failed', 0)}"
    )
