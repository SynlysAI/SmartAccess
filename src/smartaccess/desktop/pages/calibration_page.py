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

from smartaccess.desktop.viewmodels.calibration_vm import CalibrationViewModel
from smartaccess.desktop.widgets.anchor_table import AnchorRow, AnchorTable
from smartaccess.desktop.widgets.ai_dialogs import AiBusyOverlay, AiPromptDialog
from smartaccess.desktop.widgets.background_worker import BackgroundTask
from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.roi_canvas import RoiCanvas
from smartaccess.runtime.adapters.window_scanner import capture_error_reason
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.contracts.anchors import AnchorsContract

DEFAULT_VIEW_ID = "main"


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
        self._current_view_id = DEFAULT_VIEW_ID
        self._view_states: dict[str, dict] = {
            DEFAULT_VIEW_ID: {
                "title": "",
                "capture": None,
                "anchors": [],
                "capture_width": None,
                "capture_height": None,
            }
        }

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
        splitter.setSizes([280, 302, 350])
        root.addWidget(splitter, 1)

        self._canvas.roi_changed.connect(self._on_roi_changed)
        self._canvas.roi_removed.connect(self._on_roi_removed)
        self._table.row_delete_requested.connect(self._delete_anchor_row)
        self._table.row_ocr_toggled.connect(self._on_ocr_toggled)
        self._windows.itemSelectionChanged.connect(self._on_window_selected)
        self._instruments.itemDoubleClicked.connect(self._load_instrument)
        self._instruments.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._instruments.customContextMenuRequested.connect(self._instrument_menu)
        self._views.itemSelectionChanged.connect(self._on_view_selected)

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
        panel.setMinimumWidth(280)

        form = QFormLayout()
        self._device_id = QLineEdit()
        self._device_id.setPlaceholderText("device_01")
        self._title_contains = QLineEdit()
        self._title_contains.setPlaceholderText("窗口标题关键字")
        form.addRow("设备 ID", self._device_id)
        form.addRow("窗口标题", self._title_contains)
        layout.addLayout(form)

        view_title = QLabel("视图")
        view_title.setObjectName("PageHint")
        layout.addWidget(view_title)
        self._views = QListWidget()
        self._views.setMaximumHeight(92)
        layout.addWidget(self._views)
        view_row = QHBoxLayout()
        add_view_btn = QPushButton("新增视图")
        add_view_btn.setObjectName("Secondary")
        add_view_btn.clicked.connect(self._add_view)
        view_row.addWidget(add_view_btn)
        update_view_btn = QPushButton("保存当前视图")
        update_view_btn.setObjectName("Secondary")
        update_view_btn.clicked.connect(self._store_current_view)
        view_row.addWidget(update_view_btn)
        layout.addLayout(view_row)
        self._refresh_views()

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
        self._ai_busy = AiBusyOverlay()
        layout.addWidget(self._ai_busy)
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
        self._store_current_view()
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
        if self._require_device_fields(device_id=device_id, title=title) is None:
            return
        try:
            current_anchors = self._collect_anchors()
        except ValueError as exc:
            QMessageBox.warning(self, "锚点未完成", str(exc))
            return
        self._store_current_view(anchors=current_anchors)
        anchors = [
            anchor
            for state in self._view_states.values()
            for anchor in (state.get("anchors") or [])
        ]
        if not anchors:
            QMessageBox.warning(self, "缺少锚点", "请至少添加一个锚点。")
            return
        main_state = self._view_states.get(DEFAULT_VIEW_ID) or {}
        width = main_state.get("capture_width")
        height = main_state.get("capture_height")
        if width is None or height is None:
            width, height = self._canvas.source_size()
        main_capture = main_state.get("capture")
        views_payload = self._collect_views_payload(
            title=title,
            fallback_width=width,
            fallback_height=height,
            fallback_anchors=current_anchors,
        )
        view_captures = {
            view_id: state["capture"]
            for view_id, state in self._view_states.items()
            if view_id != DEFAULT_VIEW_ID and state.get("capture")
        }
        try:
            profile = self._vm.create_profile(
                device_id=device_id,
                title_contains=title,
                anchors=anchors,
                views=views_payload,
                capture_width=width,
                capture_height=height,
                capture_data=main_capture,
                view_captures=view_captures,
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

        fields = self._require_device_fields()
        if fields is None:
            return
        dialog = AiPromptDialog(
            title="AI辅助接入",
            label="描述这个软件界面里需要控制和识别的按钮、输入框、状态区域。",
            ai_label=self._vm.ai_label(),
            parent=self,
        )
        if dialog.exec() != AiPromptDialog.DialogCode.Accepted:
            return
        prompt = dialog.text_value()
        if not prompt.strip():
            return
        prompt = prompt.strip()
        device_id, title = fields
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
        self._ai_btn.setText("AI生成中")
        self._ai_busy.set_busy(True, "AI生成中，请稍候")

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
        self._ai_busy.set_busy(False)
        self._load_profile(result, capture_data=self._latest_capture)
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
        self._ai_busy.set_busy(False)
        QMessageBox.critical(self, "AI生成失败", msg)

    def _require_device_fields(
        self,
        *,
        device_id: str | None = None,
        title: str | None = None,
    ) -> tuple[str, str] | None:
        """校验设备接入所需的设备 ID 和窗口标题。"""

        device_id = (device_id if device_id is not None else self._device_id.text()).strip()
        title = (title if title is not None else self._title_contains.text()).strip()
        missing = []
        if not device_id:
            missing.append("设备 ID")
        if not title:
            missing.append("窗口标题")
        if missing:
            QMessageBox.warning(
                self,
                "缺少参数",
                "请填写：" + "、".join(missing),
            )
            return None
        return device_id, title

    def _refresh_views(self) -> None:
        """刷新设备视图列表。"""

        current = self._current_view_id
        self._views.blockSignals(True)
        self._views.clear()
        for view_id in self._view_states:
            item = QListWidgetItem(view_id)
            item.setData(Qt.ItemDataRole.UserRole, view_id)
            self._views.addItem(item)
            if view_id == current:
                self._views.setCurrentItem(item)
        self._views.blockSignals(False)

    def _add_view(self) -> None:
        """新增一个被控软件视图。"""

        self._store_current_view()
        default_name = self._next_view_name()
        view_id, ok = QInputDialog.getText(self, "新增视图", "视图 ID：", text=default_name)
        if not ok:
            return
        view_id = view_id.strip() or default_name
        if view_id in self._view_states:
            QMessageBox.warning(self, "视图重复", f"视图已存在：{view_id}")
            return
        self._view_states[view_id] = {
            "title": self._title_contains.text().strip(),
            "capture": None,
            "anchors": [],
            "capture_width": None,
            "capture_height": None,
        }
        self._current_view_id = view_id
        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._latest_capture = None
        self._refresh_views()

    def _on_view_selected(self) -> None:
        """视图切换时保存当前视图并加载目标视图。"""

        item = self._views.currentItem()
        if item is None:
            return
        view_id = item.data(Qt.ItemDataRole.UserRole)
        if not view_id or str(view_id) == self._current_view_id:
            return
        old_view_id = self._current_view_id
        self._store_current_view(view_id=old_view_id)
        self._current_view_id = str(view_id)
        self._load_view_state(self._current_view_id)

    def _store_current_view(
        self,
        *,
        view_id: str | None = None,
        anchors: list[dict] | None = None,
    ) -> None:
        """把当前画布和表格状态保存到内存视图。"""

        target = view_id or self._current_view_id
        if anchors is None:
            try:
                anchors = self._collect_anchors()
            except ValueError:
                anchors = []
        width, height = self._canvas.source_size()
        self._view_states[target] = {
            "title": self._title_contains.text().strip(),
            "capture": self._latest_capture,
            "anchors": anchors,
            "capture_width": width,
            "capture_height": height,
        }

    def _load_view_state(self, view_id: str) -> None:
        """加载指定视图的截图和锚点。"""

        state = self._view_states.get(view_id) or {}
        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._latest_capture = state.get("capture")
        if state.get("title"):
            self._title_contains.setText(str(state["title"]))
        if self._latest_capture:
            self._canvas.load_image(self._latest_capture)
        for anchor in state.get("anchors") or []:
            self._load_anchor_payload(anchor)
        self._refresh_all_roi_labels()

    def _collect_views_payload(
        self,
        *,
        title: str,
        fallback_width: int | None,
        fallback_height: int | None,
        fallback_anchors: list[dict],
    ) -> list[dict]:
        """构建设备多视图契约 payload。"""

        views = []
        if not self._view_states:
            self._view_states[DEFAULT_VIEW_ID] = {
                "title": title,
                "capture": self._latest_capture,
                "anchors": fallback_anchors,
                "capture_width": fallback_width,
                "capture_height": fallback_height,
            }
        for view_id, state in self._view_states.items():
            width = state.get("capture_width") or fallback_width
            height = state.get("capture_height") or fallback_height
            views.append(
                {
                    "view_id": view_id,
                    "window_signature": {
                        "title_contains": state.get("title") or title,
                        "screenshot_size": {"width": width, "height": height},
                    },
                    "screenshot_size": {"width": width, "height": height},
                    "anchors": state.get("anchors") or [],
                    "capture_asset_path": (
                        "capture.png"
                        if view_id == DEFAULT_VIEW_ID
                        else f"views/{view_id}/capture.png"
                    ),
                }
            )
        return views

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

    def _load_anchor_payload(self, anchor: dict) -> None:
        """把锚点 payload 加载到画布和表格。"""

        anchor_id = str(anchor.get("id") or self._next_anchor_name())
        action_region = anchor.get("action_region") or {}
        pixel = action_region.get("pixel") or {}
        self._canvas.add_roi(
            anchor_id,
            float(pixel.get("x") or 0),
            float(pixel.get("y") or 0),
            float(pixel.get("width") or 80),
            float(pixel.get("height") or 32),
        )
        observe_name = ""
        observe_region = anchor.get("observe_region")
        if isinstance(observe_region, dict):
            observe = observe_region.get("pixel") or {}
            observe_name = f"{anchor_id}_observe"
            self._canvas.add_roi(
                observe_name,
                float(observe.get("x") or 0),
                float(observe.get("y") or 0),
                float(observe.get("width") or 80),
                float(observe.get("height") or 32),
            )
        bindings = anchor.get("action_bindings") or []
        requires_confirmation = any(
            bool(binding.get("requires_confirmation"))
            for binding in bindings
            if isinstance(binding, dict)
        )
        self._table.add_anchor(
            AnchorRow(
                anchor_id=anchor_id,
                action_roi=anchor_id,
                action=self._main_action(list(anchor.get("supported_actions") or [])),
                ocr_enabled=bool(observe_name),
                observe_roi=observe_name,
                requires_confirmation=requires_confirmation,
            )
        )

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

    def _load_profile(
        self,
        profile: AnchorsContract,
        *,
        capture_data: bytes | None = None,
    ) -> None:
        """把设备配置加载到当前页面。

        Args:
            profile: 待加载的设备锚点配置。
            capture_data: 可选的当前截图；AI 草稿尚未保存时用于保留画布背景。
        """

        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._device_id.setText(profile.device_id)
        self._title_contains.setText(profile.window_signature.title_contains or "")
        self._view_states = {}
        for view in profile.views:
            view_capture = (
                capture_data
                if view.view_id == DEFAULT_VIEW_ID
                else self._vm.load_instrument_capture(
                    profile.profile_id,
                    view_id=view.view_id,
                )
            )
            self._view_states[view.view_id] = {
                "title": (
                    view.window_signature.title_contains
                    if view.window_signature is not None
                    else profile.window_signature.title_contains
                ),
                "capture": view_capture,
                "anchors": [
                    anchor.model_dump(mode="json", exclude_none=True)
                    for anchor in view.anchors
                ],
                "capture_width": (
                    view.screenshot_size.width if view.screenshot_size else None
                ),
                "capture_height": (
                    view.screenshot_size.height if view.screenshot_size else None
                ),
            }
        if DEFAULT_VIEW_ID not in self._view_states:
            self._view_states[DEFAULT_VIEW_ID] = {
                "title": profile.window_signature.title_contains or "",
                "capture": capture_data,
                "anchors": [
                    anchor.model_dump(mode="json", exclude_none=True)
                    for anchor in profile.anchors
                ],
                "capture_width": profile.window_signature.capture_width,
                "capture_height": profile.window_signature.capture_height,
            }
        self._current_view_id = DEFAULT_VIEW_ID
        self._refresh_views()
        self._latest_capture = capture_data or self._vm.load_instrument_capture(
            profile.profile_id
        )
        self._view_states[DEFAULT_VIEW_ID]["capture"] = self._latest_capture
        if self._latest_capture:
            self._canvas.load_image(self._latest_capture)
        default_view = profile.view_map().get(DEFAULT_VIEW_ID)
        anchors_to_load = default_view.anchors if default_view is not None else profile.anchors
        for anchor in anchors_to_load:
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
        self._current_view_id = DEFAULT_VIEW_ID
        self._view_states = {
            DEFAULT_VIEW_ID: {
                "title": "",
                "capture": None,
                "anchors": [],
                "capture_width": None,
                "capture_height": None,
            }
        }
        self._refresh_views()
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

    def _next_view_name(self) -> str:
        """生成下一个视图 ID。"""

        existing = set(self._view_states)
        index = 1
        while f"view_{index}" in existing:
            index += 1
        return f"view_{index}"

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
