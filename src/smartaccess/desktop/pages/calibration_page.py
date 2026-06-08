"""Device onboarding & calibration page.

Window discovery, screenshot capture, coordinate-aware ROI annotation, anchor/action
binding, and generic safety fields produce a complete ``instrument_profile.yaml``.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.viewmodels.calibration_vm import CalibrationViewModel
from smartaccess.desktop.widgets.cards import Card, page_header, section_title
from smartaccess.desktop.widgets.roi_canvas import RoiCanvas

_ALL_ACTIONS = [
    ("click", "单击"),
    ("double_click", "双击"),
    ("type", "输入文字"),
    ("hotkey", "快捷键"),
    ("wait", "等待"),
    ("wait_until", "等待条件"),
    ("screenshot_check", "截图校验"),
]
_DEFAULT_ACTIONS = {"click", "type", "hotkey", "wait_until"}
_ANCHOR_TYPES = ["action_target", "observation", "button", "input", "readout", "status", "region"]
_VISION_MODES = ["none", "ocr", "template", "presence", "color"]


class CalibrationPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = CalibrationViewModel(facade, self)
        self._windows_data: list[dict] = []
        self._selected_hwnd: int | None = None
        self._selected_title = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("设备接入与校准", "扫描窗口、截图标注、绑定动作、保存真实仪器画像"))

        body = QHBoxLayout()
        body.setSpacing(16)
        tabs = QTabWidget()
        tabs.addTab(self._build_window_tab(), "窗口")
        tabs.addTab(self._build_profile_tab(), "属性")
        tabs.addTab(self._build_anchor_tab(), "锚点")
        tabs.addTab(self._build_safety_tab(), "确认")
        body.addWidget(tabs, 2)

        right = Card()
        right.add(section_title("截图 / ROI 标注画布"))
        hint = QLabel("在截图上拖动 ROI 矩形来标记锚点区域。Ctrl+滚轮缩放，右键删除 ROI。")
        hint.setStyleSheet("color: #6b7280; font-size: 12px;")
        hint.setWordWrap(True)
        right.add(hint)
        self._canvas = RoiCanvas()
        self._canvas.roi_deleted.connect(self._on_canvas_roi_deleted)
        right.add(self._canvas)
        body.addWidget(right, 3)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        save_btn = QPushButton("生成 instrument_profile.yaml")
        save_btn.clicked.connect(self._save)
        footer.addStretch(1)
        footer.addWidget(save_btn)
        root.addLayout(footer)

        self._discover()
        self._refresh_instruments()

    def _build_window_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(section_title("① 选择仪器窗口"))
        self._windows_list = QListWidget()
        self._windows_list.itemSelectionChanged.connect(self._on_window_selected)
        layout.addWidget(self._windows_list, 1)
        row = QHBoxLayout()
        scan_btn = QPushButton("扫描窗口")
        scan_btn.clicked.connect(self._discover)
        row.addWidget(scan_btn)
        self._capture_btn = QPushButton("捕获窗口画面")
        self._capture_btn.clicked.connect(self._capture)
        self._capture_btn.setEnabled(False)
        row.addWidget(self._capture_btn)
        layout.addLayout(row)
        layout.addWidget(section_title("已校准仪器"))
        self._instruments = QListWidget()
        layout.addWidget(self._instruments)
        return page

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self._device_id = QLineEdit()
        self._device_id.setPlaceholderText("输入设备标识，如 instrument_win_01")
        self._device_id.textChanged.connect(self._auto_fill_title)
        self._title = QLineEdit()
        self._title.setPlaceholderText("选中窗口后自动填入标题")
        form.addRow("设备 ID *", self._device_id)
        form.addRow("窗口标题包含 *", self._title)
        layout.addLayout(form)
        layout.addWidget(section_title("仪器级能力"))
        self._actions: dict[str, QCheckBox] = {}
        for key, label in _ALL_ACTIONS:
            cb = QCheckBox(f"{key} — {label}")
            cb.setChecked(key in _DEFAULT_ACTIONS)
            self._actions[key] = cb
            layout.addWidget(cb)
        layout.addStretch(1)
        return page

    def _build_anchor_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(section_title("③ 锚点、ROI 与动作绑定"))
        self._anchor_table = QTableWidget(0, 7)
        self._anchor_table.setHorizontalHeaderLabels(["锚点", "类型", "ROI", "动作", "识别", "确认", ""])
        self._anchor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._anchor_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._anchor_table, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("+ 添加锚点")
        add_btn.clicked.connect(self._add_anchor)
        row.addWidget(add_btn)
        sync_btn = QPushButton("同步坐标")
        sync_btn.setObjectName("Ghost")
        sync_btn.clicked.connect(self._refresh_anchor_coordinates)
        row.addWidget(sync_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(section_title("需人工确认的步骤 / 通用安全字段"))
        self._safety_table = QTableWidget(0, 5)
        self._safety_table.setHorizontalHeaderLabels(["字段/步骤", "显示名称", "类型", "风险", "确认"])
        self._safety_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._safety_table, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("+ 添加确认项")
        add_btn.clicked.connect(self._add_safety_field)
        row.addWidget(add_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _discover(self) -> None:
        self._windows_list.clear()
        self._windows_data.clear()
        try:
            windows = self._vm.discover_windows()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "扫描失败", f"扫描窗口时发生异常：{exc}")
            return
        for win in windows:
            self._windows_data.append({"title": win.title, "hwnd": win.hwnd, "w": win.width, "h": win.height})
            self._windows_list.addItem(f"  {win.title}  ({win.width}×{win.height})")
        if not windows:
            self._windows_list.addItem("未发现可用窗口，请确认仪器软件已打开")

    def _on_window_selected(self) -> None:
        row = self._windows_list.currentRow()
        if row < 0 or row >= len(self._windows_data):
            return
        self._selected_hwnd = self._windows_data[row]["hwnd"]
        self._selected_title = self._windows_data[row]["title"]
        self._capture_btn.setEnabled(self._selected_hwnd is not None)
        self._title.setText(self._selected_title)

    def _auto_fill_title(self) -> None:
        if not self._title.text().strip() and self._selected_title:
            self._title.setText(self._selected_title)

    def _capture(self) -> None:
        if self._selected_hwnd is None:
            QMessageBox.warning(self, "未选择窗口", "请先在左侧窗口列表中选中一个窗口。")
            return
        try:
            data = self._vm.capture_window(self._selected_hwnd)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "截图失败", f"截图时发生异常：{exc}")
            return
        if data is None:
            from smartaccess.runtime.adapters.window_scanner import capture_error_reason
            reason = capture_error_reason()
            self._canvas.load_placeholder(f"截图失败：{reason}")
            QMessageBox.warning(self, "截图失败", reason)
            return
        self._canvas.load_image(data)
        self._refresh_anchor_coordinates()

    def _add_anchor(self) -> None:
        name, ok = QInputDialog.getText(self, "添加锚点", "锚点名称（如 anchor_start_button）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        roi_name = name
        self._canvas.add_roi(roi_name)
        self._insert_anchor_row(name=name, roi_name=roi_name)

    def _insert_anchor_row(self, *, name: str, roi_name: str) -> None:
        row = self._anchor_table.rowCount()
        self._anchor_table.insertRow(row)
        self._anchor_table.setItem(row, 0, QTableWidgetItem(name))
        type_box = QComboBox()
        type_box.addItems(_ANCHOR_TYPES)
        self._anchor_table.setCellWidget(row, 1, type_box)
        self._anchor_table.setItem(row, 2, QTableWidgetItem(roi_name))
        action_box = QComboBox()
        action_box.addItems([a[0] for a in _ALL_ACTIONS])
        self._anchor_table.setCellWidget(row, 3, action_box)
        vision_box = QComboBox()
        vision_box.addItems(_VISION_MODES)
        self._anchor_table.setCellWidget(row, 4, vision_box)
        confirm = QCheckBox()
        self._anchor_table.setCellWidget(row, 5, confirm)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
        self._anchor_table.setCellWidget(row, 6, del_btn)
        self._refresh_anchor_coordinates()

    def _delete_anchor(self, row: int) -> None:
        roi_item = self._anchor_table.item(row, 2)
        if roi_item:
            self._canvas.remove_roi(roi_item.text().split("  ")[0].strip())
        self._anchor_table.removeRow(row)
        self._rebind_delete_buttons()

    def _on_canvas_roi_deleted(self, roi_name: str) -> None:
        for row in range(self._anchor_table.rowCount()):
            item = self._anchor_table.item(row, 2)
            if item and item.text() == roi_name:
                self._anchor_table.removeRow(row)
                self._rebind_delete_buttons()
                return

    def _rebind_delete_buttons(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            btn = QPushButton("删除")
            btn.setObjectName("Ghost")
            btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
            self._anchor_table.setCellWidget(row, 6, btn)

    def _refresh_anchor_coordinates(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            roi_item = self._anchor_table.item(row, 2)
            if not roi_item:
                continue
            rect = self._canvas.roi_rect(roi_item.text())
            if rect:
                roi_item.setText(
                    f"{roi_item.text().split('  ')[0]}  ({rect['x']:.0f},{rect['y']:.0f},{rect['width']:.0f},{rect['height']:.0f})"
                )

    def _add_safety_field(self) -> None:
        row = self._safety_table.rowCount()
        self._safety_table.insertRow(row)
        self._safety_table.setItem(row, 0, QTableWidgetItem("start_run"))
        self._safety_table.setItem(row, 1, QTableWidgetItem("启动运行"))
        type_box = QComboBox()
        type_box.addItems(["string", "number", "bool", "choice"])
        type_box.setCurrentText("bool")
        self._safety_table.setCellWidget(row, 2, type_box)
        risk_box = QComboBox()
        risk_box.addItems(["low", "medium", "high"])
        risk_box.setCurrentText("high")
        self._safety_table.setCellWidget(row, 3, risk_box)
        confirm = QCheckBox()
        confirm.setChecked(True)
        self._safety_table.setCellWidget(row, 4, confirm)

    def _save(self) -> None:
        device_id = self._device_id.text().strip()
        title = self._title.text().strip()
        if not device_id:
            QMessageBox.warning(self, "缺少设备 ID", "请输入设备标识。")
            return
        if not title:
            QMessageBox.warning(self, "缺少窗口标题", "请输入或选择窗口标题。")
            return
        anchors = self._collect_anchors()
        if not anchors:
            QMessageBox.warning(self, "缺少锚点", "请至少添加一个锚点并保存 ROI 坐标。")
            return
        actions = [key for key, cb in self._actions.items() if cb.isChecked()] or list(_DEFAULT_ACTIONS)
        safety_fields, confirm_steps = self._collect_safety_fields(anchors)
        w, h = self._canvas.source_size()
        try:
            profile = self._vm.create_profile(
                device_id=device_id,
                title_contains=title,
                anchors=anchors,
                actions=actions,
                safety_fields=safety_fields,
                confirm_steps=confirm_steps,
                capture_width=w,
                capture_height=h,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._refresh_instruments()
        QMessageBox.information(self, "校准完成", f"已生成仪器画像: {profile.device_id}\n锚点: {len(profile.anchors)} 个")

    def _collect_anchors(self) -> list[dict]:
        anchors: list[dict] = []
        for row in range(self._anchor_table.rowCount()):
            name_item = self._anchor_table.item(row, 0)
            roi_item = self._anchor_table.item(row, 2)
            if not name_item or not roi_item:
                continue
            name = name_item.text().strip()
            roi_name = roi_item.text().split("  ")[0].strip()
            rect = self._canvas.roi_rect(roi_name)
            norm = self._canvas.normalized_roi_rect(roi_name)
            type_box = self._anchor_table.cellWidget(row, 1)
            action_box = self._anchor_table.cellWidget(row, 3)
            vision_box = self._anchor_table.cellWidget(row, 4)
            confirm = self._anchor_table.cellWidget(row, 5)
            action = action_box.currentText() if isinstance(action_box, QComboBox) else "click"
            anchors.append(
                {
                    "id": name,
                    "type": type_box.currentText() if isinstance(type_box, QComboBox) else "action_target",
                    "locator_hint": roi_name,
                    "roi": rect,
                    "normalized_roi": norm,
                    "action_bindings": [
                        {
                            "action": action,
                            "requires_confirmation": confirm.isChecked() if isinstance(confirm, QCheckBox) else False,
                        }
                    ],
                    "vision_mode": vision_box.currentText() if isinstance(vision_box, QComboBox) else "none",
                    "confidence_threshold": 0.7,
                }
            )
        return anchors

    def _collect_safety_fields(self, anchors: list[dict]) -> tuple[list[dict], list[str]]:
        fields: list[dict] = []
        confirm_steps: list[str] = []
        for anchor in anchors:
            for binding in anchor.get("action_bindings", []):
                if binding.get("requires_confirmation"):
                    confirm_steps.append(anchor["id"])
        for row in range(self._safety_table.rowCount()):
            field_item = self._safety_table.item(row, 0)
            label_item = self._safety_table.item(row, 1)
            if not field_item or not label_item:
                continue
            type_box = self._safety_table.cellWidget(row, 2)
            risk_box = self._safety_table.cellWidget(row, 3)
            confirm = self._safety_table.cellWidget(row, 4)
            field_id = field_item.text().strip()
            if not field_id:
                continue
            if isinstance(confirm, QCheckBox) and confirm.isChecked():
                confirm_steps.append(field_id)
            fields.append(
                {
                    "field_id": field_id,
                    "label": label_item.text().strip() or field_id,
                    "value_type": type_box.currentText() if isinstance(type_box, QComboBox) else "string",
                    "risk_level": risk_box.currentText() if isinstance(risk_box, QComboBox) else "medium",
                    "requires_confirmation": confirm.isChecked() if isinstance(confirm, QCheckBox) else False,
                    "applies_to_steps": [field_id],
                }
            )
        return fields, sorted(set(confirm_steps))

    def _refresh_instruments(self) -> None:
        self._instruments.clear()
        for profile in self._vm.list_instruments():
            self._instruments.addItem(f"{profile.device_id}  ·  锚点 {len(profile.anchors)}  ·  动作 {', '.join(profile.actions)}")
        if self._instruments.count() == 0:
            self._instruments.addItem("尚无已校准仪器")
