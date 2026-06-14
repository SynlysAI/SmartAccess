"""设备接入与校准页面。"""

from __future__ import annotations

import base64

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from smartaccess_v2.desktop.viewmodels.calibration_vm import CalibrationViewModel
from smartaccess_v2.desktop.widgets.anchor_table import AnchorRow, AnchorTable
from smartaccess_v2.desktop.widgets.background_worker import BackgroundTask
from smartaccess_v2.desktop.widgets.cards import create_card
from smartaccess_v2.desktop.widgets.roi_canvas import RoiCanvas
from smartaccess_v2.runtime.adapters.window_scanner import capture_error_reason
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.contracts.anchors import AnchorsContract


class CalibrationPage(QWidget):
    """设备窗口扫描、截图、ROI 标注和锚点保存页面。"""

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化校准页面。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(parent)
        self._vm = CalibrationViewModel(facade, self)
        self._windows_data: list[dict] = []
        self._selected_hwnd: int | None = None
        self._selected_title = ""
        self._latest_capture: bytes | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 302, 350])
        root.addWidget(splitter, 1)

        self._canvas.roi_changed.connect(self._on_roi_changed)
        self._canvas.roi_removed.connect(self._on_roi_removed)
        self._table.row_delete_requested.connect(self._delete_anchor_row)
        self._table.row_ocr_toggled.connect(self._on_ocr_toggled)
        self._windows.itemSelectionChanged.connect(self._on_window_selected)
        self._instruments.itemDoubleClicked.connect(self._load_instrument)
        self._instruments.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._instruments.customContextMenuRequested.connect(self._instrument_menu)

        self._discover()
        self._refresh_instruments()

    def on_show(self) -> None:
        """页面显示时刷新设备列表。"""

        self._refresh_instruments()

    def _build_header(self) -> QHBoxLayout:
        """构建页面顶部区域。"""

        row = QHBoxLayout()
        title = QLabel("设备接入与校准")
        title.setObjectName("PageTitle")
        row.addWidget(title)
        row.addStretch(1)
        new_btn = QPushButton("新建")
        new_btn.setObjectName("Secondary")
        new_btn.clicked.connect(self._new_profile)
        row.addWidget(new_btn)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return row

    def _build_left_panel(self) -> QWidget:
        """构建左侧设备和窗口面板。"""

        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(220)

        form = QFormLayout()
        self._device_id = QLineEdit()
        self._device_id.setPlaceholderText("device_01")
        self._title_contains = QLineEdit()
        self._title_contains.setPlaceholderText("窗口标题关键字")
        form.addRow("设备 ID", self._device_id)
        form.addRow("窗口标题", self._title_contains)
        layout.addLayout(form)

        window_title = QLabel("窗口")
        window_title.setObjectName("PageHint")
        layout.addWidget(window_title)
        self._windows = QListWidget()
        layout.addWidget(self._windows, 1)
        scan_row = QHBoxLayout()
        scan_btn = QPushButton("扫描")
        scan_btn.setObjectName("Secondary")
        scan_btn.clicked.connect(self._discover)
        scan_row.addWidget(scan_btn)
        self._capture_btn = QPushButton("截图")
        self._capture_btn.setEnabled(False)
        self._capture_btn.clicked.connect(self._capture)
        scan_row.addWidget(self._capture_btn)
        layout.addLayout(scan_row)

        instruments_title = QLabel("已保存设备")
        instruments_title.setObjectName("PageHint")
        layout.addWidget(instruments_title)
        self._instruments = QListWidget()
        layout.addWidget(self._instruments, 1)
        return panel

    def _build_center_panel(self) -> QWidget:
        """构建中间 ROI 画布区域。"""

        panel, layout = create_card(margins=(10, 10, 10, 10), spacing=8)
        panel.setMinimumSize(100, 100)
        self._canvas = RoiCanvas()
        self._canvas.setMinimumSize(80, 80)
        layout.addWidget(self._canvas, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右侧锚点表格区域。"""

        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(350)
        row = QHBoxLayout()
        add_btn = QPushButton("添加锚点")
        add_btn.setObjectName("TableToolbarButton")
        add_btn.clicked.connect(self._add_anchor)
        row.addWidget(add_btn)
        self._ai_btn = QPushButton("AI辅助接入")
        self._ai_btn.setObjectName("TableToolbarButton")
        self._ai_btn.clicked.connect(self._ai_assist)
        row.addWidget(self._ai_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self._table = AnchorTable()
        layout.addWidget(self._table, 1)
        return panel

    def _discover(self) -> None:
        """扫描窗口列表。"""

        self._windows.clear()
        self._windows_data.clear()
        try:
            windows = self._vm.discover_windows()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "扫描失败", str(exc))
            return
        for window in windows:
            self._windows_data.append(
                {
                    "title": window.title,
                    "hwnd": window.hwnd,
                    "width": window.width,
                    "height": window.height,
                }
            )
            item = QListWidgetItem(f"{window.title}  ({window.width}x{window.height})")
            self._windows.addItem(item)
        if not windows:
            self._windows.addItem("未发现可用窗口")

    def _on_window_selected(self) -> None:
        """窗口选中变化时同步标题和截图按钮。"""

        row = self._windows.currentRow()
        if row < 0 or row >= len(self._windows_data):
            self._selected_hwnd = None
            self._capture_btn.setEnabled(False)
            return
        data = self._windows_data[row]
        self._selected_hwnd = data["hwnd"]
        self._selected_title = data["title"]
        self._capture_btn.setEnabled(self._selected_hwnd is not None)
        self._title_contains.setText(self._selected_title)

    def _capture(self) -> None:
        """捕获选中窗口截图。"""

        if self._selected_hwnd is None:
            QMessageBox.warning(self, "未选择窗口", "请先选择窗口。")
            return
        try:
            data = self._vm.capture_window(self._selected_hwnd)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "截图失败", str(exc))
            return
        if data is None:
            reason = capture_error_reason()
            self._canvas.load_placeholder(f"截图失败：{reason}")
            QMessageBox.warning(self, "截图失败", reason)
            return
        self._latest_capture = data
        self._canvas.load_image(data)
        self._refresh_all_roi_labels()

    def _add_anchor(self) -> None:
        """添加一个锚点和动作 ROI。"""

        default_name = self._next_anchor_name()
        name, ok = QInputDialog.getText(self, "添加锚点", "锚点 ID：", text=default_name)
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name in self._canvas.roi_names():
            QMessageBox.warning(self, "锚点重复", f"ROI 已存在：{name}")
            return
        self._canvas.add_roi(name)
        self._table.add_anchor(AnchorRow(anchor_id=name, action_roi=name))
        self._refresh_all_roi_labels()

    def _delete_anchor_row(self, row: int) -> None:
        """删除锚点行及其 ROI。"""

        row_data = self._table.remove_row(row)
        if row_data is None:
            return
        self._canvas.remove_roi(row_data.action_roi, emit_signal=False)
        if row_data.observe_roi:
            self._canvas.remove_roi(row_data.observe_roi, emit_signal=False)
        self._refresh_all_roi_labels()

    def _on_ocr_toggled(self, row: int, checked: bool) -> None:
        """开关 OCR 时同步观察 ROI。"""

        row_data = self._table.row_model(row)
        if row_data is None:
            return
        if checked:
            observe_name = row_data.observe_roi or f"{row_data.anchor_id}_observe"
            if observe_name not in self._canvas.roi_names():
                rect = self._canvas.roi_rect(row_data.action_roi) or {
                    "x": 60,
                    "y": 80,
                    "width": 180,
                    "height": 70,
                }
                self._canvas.add_roi(
                    observe_name,
                    rect["x"] + 24,
                    rect["y"] + 24,
                    rect["width"],
                    rect["height"],
                )
            self._table.set_observe_roi(row, observe_name)
            self._table.update_roi_label(observe_name, self._roi_label(observe_name))
        else:
            removed = self._table.clear_observe_roi(row)
            if removed:
                self._canvas.remove_roi(removed, emit_signal=False)
            fallback_name = f"{row_data.anchor_id}_observe"
            if fallback_name != removed:
                self._canvas.remove_roi(fallback_name, emit_signal=False)
        self._refresh_all_roi_labels()

    def _on_roi_removed(self, roi_name: str) -> None:
        """画布删除 ROI 后同步表格。"""

        for row_data in self._table.row_models():
            if row_data.action_roi == roi_name and row_data.observe_roi:
                self._canvas.remove_roi(row_data.observe_roi, emit_signal=False)
        self._table.remove_rows_by_roi(roi_name)
        self._refresh_all_roi_labels()

    def _on_roi_changed(self, roi_name: str) -> None:
        """ROI 坐标变化后实时同步表格。"""

        self._table.update_roi_label(roi_name, self._roi_label(roi_name))

    def _refresh_all_roi_labels(self) -> None:
        """刷新表格中所有 ROI 坐标显示。"""

        for roi_name in self._canvas.roi_names():
            self._table.update_roi_label(roi_name, self._roi_label(roi_name))

    def _roi_label(self, roi_name: str) -> str:
        """生成 ROI 短坐标文本。"""

        rect = self._canvas.roi_rect(roi_name)
        if not rect:
            return roi_name
        return (
            f"({rect['x']:.0f},{rect['y']:.0f},"
            f"{rect['width']:.0f},{rect['height']:.0f})"
        )

    def _save(self) -> None:
        """保存当前设备锚点配置。"""

        device_id = self._device_id.text().strip()
        title = self._title_contains.text().strip()
        if not device_id:
            QMessageBox.warning(self, "缺少设备 ID", "请输入设备 ID。")
            return
        if not title:
            QMessageBox.warning(self, "缺少窗口标题", "请输入窗口标题关键字。")
            return
        try:
            anchors = self._collect_anchors()
        except ValueError as exc:
            QMessageBox.warning(self, "锚点未完成", str(exc))
            return
        if not anchors:
            QMessageBox.warning(self, "缺少锚点", "请至少添加一个锚点。")
            return
        width, height = self._canvas.source_size()
        try:
            profile = self._vm.create_profile(
                device_id=device_id,
                title_contains=title,
                anchors=anchors,
                capture_width=width,
                capture_height=height,
                capture_data=self._latest_capture,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._refresh_instruments()
        QMessageBox.information(
            self,
            "已保存",
            f"设备 {profile.device_id} 已保存，锚点数：{len(profile.anchors)}",
        )

    def _ai_assist(self) -> None:
        """调用 AI 生成设备锚点草稿并加载到页面。"""

        prompt, ok = QInputDialog.getMultiLineText(
            self,
            "AI辅助接入",
            (
                "描述这个软件界面里需要控制和识别的按钮、输入框、状态区域。\n"
                f"当前 AI：{self._vm.ai_label()}"
            ),
            "",
        )
        if not ok or not prompt.strip():
            return
        prompt = prompt.strip()
        device_id = self._device_id.text().strip() or "new_device"
        title = self._title_contains.text().strip() or self._selected_title
        width, height = self._canvas.source_size()
        context = {
            "device_id": device_id,
            "title_contains": title,
            "window_title": self._selected_title,
            "capture_width": width,
            "capture_height": height,
        }
        if self._latest_capture:
            context["screenshot"] = {
                "mime_type": "image/png",
                "data": base64.b64encode(self._latest_capture).decode("ascii"),
            }

        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("生成中...")

        self._ai_task = BackgroundTask(
            lambda: self._vm.draft_profile(prompt, context), parent=self
        )
        self._ai_task.done.connect(self._on_ai_assist_done)
        self._ai_task.error.connect(self._on_ai_assist_error)
        self._ai_task.start()

    def _on_ai_assist_done(self, result: object) -> None:
        """AI 辅助接入完成后的回调。"""

        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI辅助接入")
        self._load_profile(result)
        reasoning = self._vm.ai_reasoning()
        QMessageBox.information(
            self,
            "AI建议已加载",
            f"已生成 {len(result.anchors)} 个锚点。\n\n{reasoning[:800]}",
        )

    def _on_ai_assist_error(self, msg: str) -> None:
        """AI 辅助接入失败后的回调。"""

        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI辅助接入")
        QMessageBox.critical(self, "AI生成失败", msg)

    def _collect_anchors(self) -> list[dict]:
        """从表格和画布收集锚点契约数据。"""

        anchors: list[dict] = []
        for row in self._table.row_models():
            rect = self._canvas.roi_rect(row.action_roi)
            norm = self._canvas.normalized_roi_rect(row.action_roi)
            if rect is None or norm is None:
                raise ValueError(f"锚点 {row.anchor_id} 缺少动作 ROI")
            observe_region = None
            if row.ocr_enabled:
                observe_rect = self._canvas.roi_rect(row.observe_roi)
                observe_norm = self._canvas.normalized_roi_rect(row.observe_roi)
                if observe_rect is None or observe_norm is None:
                    raise ValueError(f"锚点 {row.anchor_id} 已开启 OCR，但缺少观察 ROI")
                observe_region = {"pixel": observe_rect, "normalized": observe_norm}
            supported_actions = self._supported_actions(row.action)
            anchors.append(
                {
                    "id": row.anchor_id,
                    "action_region": {"pixel": rect, "normalized": norm},
                    "observe_region": observe_region,
                    "supported_actions": supported_actions,
                    "default_wait_seconds": 2.0,
                    "action_bindings": [
                        {
                            "action": action,
                            "requires_confirmation": row.requires_confirmation,
                        }
                        for action in supported_actions
                    ],
                }
            )
        return anchors

    def _refresh_instruments(self) -> None:
        """刷新已保存设备列表。"""

        self._instruments.clear()
        for profile in self._vm.list_instruments():
            item = QListWidgetItem(
                f"{profile.device_id}  ·  锚点 {len(profile.anchors)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, profile.device_id)
            self._instruments.addItem(item)
        if self._instruments.count() == 0:
            self._instruments.addItem("暂无已保存设备")

    def _load_instrument(self, item: QListWidgetItem) -> None:
        """加载已保存设备配置。"""

        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return
        profile = self._vm.get_instrument(str(device_id))
        if profile is None:
            QMessageBox.warning(self, "加载失败", f"找不到设备：{device_id}")
            return
        self._load_profile(profile)

    def _load_profile(self, profile: AnchorsContract) -> None:
        """把设备配置加载到当前页面。"""

        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._device_id.setText(profile.device_id)
        self._title_contains.setText(profile.window_signature.title_contains or "")
        self._latest_capture = self._vm.load_instrument_capture(profile.profile_id)
        if self._latest_capture:
            self._canvas.load_image(self._latest_capture)
        for anchor in profile.anchors:
            pixel = anchor.action_region.pixel
            self._canvas.add_roi(
                anchor.id,
                pixel.x,
                pixel.y,
                pixel.width,
                pixel.height,
            )
            observe_name = ""
            if anchor.observe_region is not None:
                observe_name = f"{anchor.id}_observe"
                observe = anchor.observe_region.pixel
                self._canvas.add_roi(
                    observe_name,
                    observe.x,
                    observe.y,
                    observe.width,
                    observe.height,
                )
            requires_confirmation = any(
                binding.requires_confirmation for binding in anchor.action_bindings
            )
            self._table.add_anchor(
                AnchorRow(
                    anchor_id=anchor.id,
                    action_roi=anchor.id,
                    action=self._main_action(list(anchor.supported_actions)),
                    ocr_enabled=bool(observe_name),
                    observe_roi=observe_name,
                    requires_confirmation=requires_confirmation,
                )
            )
        self._refresh_all_roi_labels()

    def _new_profile(self) -> None:
        """清空当前设备编辑状态。"""

        self._selected_hwnd = None
        self._selected_title = ""
        self._latest_capture = None
        self._device_id.clear()
        self._title_contains.clear()
        self._capture_btn.setEnabled(False)
        self._windows.blockSignals(True)
        self._windows.clearSelection()
        self._windows.setCurrentRow(-1)
        self._windows.blockSignals(False)
        self._canvas.clear_all()
        self._table.setRowCount(0)

    def _instrument_menu(self, pos) -> None:
        """显示设备列表右键菜单。"""

        item = self._instruments.itemAt(pos)
        if item is None:
            return
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return
        menu = QMenu(self)
        load_action = menu.addAction("加载")
        delete_action = menu.addAction("删除")
        action = menu.exec(self._instruments.mapToGlobal(pos))
        if action == load_action:
            self._load_instrument(item)
        elif action == delete_action:
            self._delete_instrument(str(device_id))

    def _delete_instrument(self, device_id: str) -> None:
        """删除保存的设备配置。"""

        reply = QMessageBox.question(
            self,
            "删除设备",
            f"确认删除设备 {device_id}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._vm.delete_instrument(device_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self._refresh_instruments()

    def _next_anchor_name(self) -> str:
        """生成下一个锚点名称。"""

        existing = set(self._canvas.roi_names())
        index = 1
        while f"anchor_{index}" in existing:
            index += 1
        return f"anchor_{index}"

    @staticmethod
    def _supported_actions(action: str) -> list[str]:
        """按主动作推导支持动作集合。"""

        if action == "type":
            return ["click", "type", "hotkey", "press_enter"]
        if action == "hotkey":
            return ["click", "hotkey"]
        if action == "press_enter":
            return ["click", "press_enter"]
        return ["click"]

    @staticmethod
    def _main_action(actions: list[str]) -> str:
        """按支持动作推导主动作。"""

        if "type" in actions:
            return "type"
        if "hotkey" in actions:
            return "hotkey"
        if "press_enter" in actions:
            return "press_enter"
        return "click"
