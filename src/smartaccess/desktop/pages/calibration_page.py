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
from smartaccess.runtime.adapters.window_scanner import (
    capture_error_reason,
    capture_metadata,
)
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.contracts.anchors import (
    AnchorDefinition,
    AnchorsContract,
    AnchorView,
)

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
        self._latest_capture_metadata: dict[str, object] = {}
        self._current_view_id = DEFAULT_VIEW_ID
        self._ai_target_view_id: str | None = None
        self._view_states: dict[str, dict] = {
            DEFAULT_VIEW_ID: {
                "title": "",
                "capture": None,
                "anchors": [],
                "capture_width": None,
                "capture_height": None,
                "capture_metadata": {},
                "capture_windows": [],
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
        self._windows.itemChanged.connect(self._on_window_checked)
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
        ocr_btn = QPushButton("OCR预览")
        ocr_btn.setObjectName("TableToolbarButton")
        ocr_btn.clicked.connect(self._preview_current_view_ocr)
        row.addWidget(ocr_btn)
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
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
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

    def _on_window_checked(self, _item: QListWidgetItem) -> None:
        """窗口勾选变化时同步截图按钮状态。"""

        has_checked = bool(self._checked_window_hwnds())
        self._capture_btn.setEnabled(has_checked or self._selected_hwnd is not None)

    def _capture(self) -> None:
        """捕获选中窗口或多窗口联合截图。"""

        hwnds = self._ordered_capture_hwnds()
        if not hwnds and self._selected_hwnd is not None:
            hwnds = [self._selected_hwnd]
        if not hwnds:
            QMessageBox.warning(self, "未选择窗口", "请先选择窗口。")
            return
        try:
            data = (
                self._vm.capture_window(hwnds[0])
                if len(hwnds) == 1
                else self._vm.capture_windows(hwnds)
            )
        except Exception as exc:  # noqa: BLE001
            self._restore_page_focus()
            QMessageBox.critical(self, "截图失败", str(exc))
            return
        self._restore_page_focus()
        if data is None:
            reason = capture_error_reason()
            self._canvas.load_placeholder(f"截图失败：{reason}")
            QMessageBox.warning(self, "截图失败", reason)
            return
        self._latest_capture = data
        self._latest_capture_metadata = capture_metadata()
        self._latest_capture_metadata["capture_mode"] = (
            "screen_canvas" if len(hwnds) > 1 else "window"
        )
        self._latest_capture_metadata["window_count"] = len(hwnds)
        self._canvas.load_image(data)
        self._store_current_view()
        self._refresh_all_roi_labels()

    def _checked_window_hwnds(self) -> list[int]:
        """返回当前勾选的窗口句柄。"""

        hwnds: list[int] = []
        for row, data in enumerate(self._windows_data):
            item = self._windows.item(row)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked and data.get("hwnd"):
                hwnds.append(int(data["hwnd"]))
        return hwnds

    def _ordered_capture_hwnds(self) -> list[int]:
        """返回用于截图的窗口句柄顺序，当前选中窗口最后前置。"""

        hwnds = self._checked_window_hwnds()
        if self._selected_hwnd is None or self._selected_hwnd not in hwnds:
            return hwnds
        return [hwnd for hwnd in hwnds if hwnd != self._selected_hwnd] + [
            self._selected_hwnd,
        ]

    def _preview_current_view_ocr(self) -> None:
        """对当前视图第一个 OCR 锚点做一次识别预览。"""

        try:
            anchors = self._collect_anchors()
        except ValueError as exc:
            QMessageBox.warning(self, "OCR预览失败", str(exc))
            return
        anchor = next(
            (item for item in anchors if item.get("observe_region") is not None),
            None,
        )
        if anchor is None:
            QMessageBox.warning(self, "OCR预览失败", "当前视图没有开启 OCR 的锚点。")
            return
        capture_data = self._latest_capture
        if capture_data is None:
            state = self._view_states.get(self._current_view_id) or {}
            capture_data = state.get("capture")
        if capture_data is None:
            QMessageBox.warning(self, "OCR预览失败", "请先刷新当前视图截图。")
            return
        try:
            text = self._vm.preview_anchor_ocr(
                capture_data=capture_data,
                anchor_payload=anchor,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "OCR预览失败", str(exc))
            return
        QMessageBox.information(
            self,
            "OCR预览",
            f"锚点：{anchor.get('id')}\n识别文本：{text or '-'}",
        )

    def _restore_page_focus(self) -> None:
        """截图后把焦点切回 SmartAccess 页面。"""

        window = self.window()
        window.showNormal()
        window.raise_()
        window.activateWindow()

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
        main_title = str(main_state.get("title") or "").strip()
        if not main_title:
            main_title = title if self._current_view_id == DEFAULT_VIEW_ID else ""
        if not main_title:
            QMessageBox.warning(
                self,
                "缺少主窗口标题",
                "请先在 main 视图保存主窗口标题，再保存弹窗视图。",
            )
            return
        width = main_state.get("capture_width")
        height = main_state.get("capture_height")
        if width is None or height is None:
            width, height = self._canvas.source_size()
        main_capture = main_state.get("capture")
        views_payload = self._collect_views_payload(
            title=main_title,
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
            main_metadata = main_state.get("capture_metadata") or {}
            main_origin_x, main_origin_y = self._legacy_capture_origin(main_metadata)
            profile = self._vm.create_profile(
                device_id=device_id,
                title_contains=main_title,
                anchors=anchors,
                views=views_payload,
                capture_width=width,
                capture_height=height,
                capture_origin_x=main_origin_x,
                capture_origin_y=main_origin_y,
                capture_mode=str(main_metadata.get("capture_mode") or "window"),
                capture_screen_origin_x=main_metadata.get("origin_x"),
                capture_screen_origin_y=main_metadata.get("origin_y"),
                capture_windows=main_state.get("capture_windows") or [],
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
        self._ai_target_view_id = self._current_view_id

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
        target_view_id = self._ai_target_view_id or self._current_view_id
        applied_count = self._apply_ai_profile_to_view(
            result,
            target_view_id=target_view_id,
        )
        self._ai_target_view_id = None
        reasoning = self._vm.ai_reasoning()
        QMessageBox.information(
            self,
            "AI建议已加载",
            f"已生成 {applied_count} 个锚点。\n\n{reasoning[:800]}",
        )

    def _on_ai_assist_error(self, msg: str) -> None:
        """AI 辅助接入失败后的回调。"""

        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI辅助接入")
        self._ai_busy.set_busy(False)
        self._ai_target_view_id = None
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
            "capture_metadata": {},
            "capture_windows": [],
        }
        self._current_view_id = view_id
        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._latest_capture = None
        self._latest_capture_metadata = {}
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
            "capture_metadata": dict(self._latest_capture_metadata),
            "capture_windows": self._selected_capture_windows(),
        }

    def _load_view_state(self, view_id: str) -> None:
        """加载指定视图的截图和锚点。"""

        state = self._view_states.get(view_id) or {}
        self._canvas.clear_all()
        self._table.setRowCount(0)
        self._latest_capture = state.get("capture")
        self._latest_capture_metadata = dict(state.get("capture_metadata") or {})
        if state.get("title"):
            self._title_contains.setText(str(state["title"]))
        if self._latest_capture:
            self._canvas.load_image(self._latest_capture)
        for anchor in state.get("anchors") or []:
            self._load_anchor_payload(anchor)
        self._refresh_all_roi_labels()

    def _apply_ai_profile_to_view(
        self,
        profile: AnchorsContract,
        *,
        target_view_id: str,
    ) -> int:
        """Apply an AI anchor draft to one view without replacing the profile."""

        ai_view = self._ai_view_for_target(profile, target_view_id)
        anchor_models = ai_view.anchors if ai_view is not None else profile.anchors
        anchors = self._anchor_payloads(anchor_models)
        existing = self._view_states.get(target_view_id) or {}
        width = existing.get("capture_width")
        height = existing.get("capture_height")
        if (width is None or height is None) and ai_view is not None:
            if ai_view.screenshot_size is not None:
                width = ai_view.screenshot_size.width if width is None else width
                height = ai_view.screenshot_size.height if height is None else height
            if ai_view.window_signature is not None:
                width = ai_view.window_signature.capture_width if width is None else width
                height = ai_view.window_signature.capture_height if height is None else height
        if (width is None or height is None) and profile.window_signature is not None:
            width = profile.window_signature.capture_width if width is None else width
            height = profile.window_signature.capture_height if height is None else height
        if width is None or height is None:
            source_width, source_height = self._canvas.source_size()
            width = source_width if width is None else width
            height = source_height if height is None else height

        self._view_states[target_view_id] = {
            "title": existing.get("title") or self._title_contains.text().strip(),
            "capture": existing.get("capture"),
            "anchors": anchors,
            "capture_width": width,
            "capture_height": height,
            "capture_metadata": existing.get("capture_metadata") or {},
            "capture_windows": existing.get("capture_windows") or [],
        }
        self._refresh_views()
        if target_view_id == self._current_view_id:
            self._load_view_state(target_view_id)
        return len(anchors)

    def _ai_view_for_target(
        self,
        profile: AnchorsContract,
        target_view_id: str,
    ) -> AnchorView | None:
        """Return the matching AI view, falling back to default main output."""

        view_map = profile.view_map()
        return view_map.get(target_view_id) or view_map.get(DEFAULT_VIEW_ID)

    @staticmethod
    def _anchor_payloads(anchors: list[AnchorDefinition]) -> list[dict]:
        """Convert anchor models to UI state payloads."""

        return [
            anchor.model_dump(mode="json", exclude_none=True)
            for anchor in anchors
        ]

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
                "capture_metadata": dict(self._latest_capture_metadata),
                "capture_windows": self._selected_capture_windows(),
            }
        for view_id, state in self._view_states.items():
            width = state.get("capture_width") or fallback_width
            height = state.get("capture_height") or fallback_height
            metadata = state.get("capture_metadata") or {}
            origin_x, origin_y = self._legacy_capture_origin(metadata)
            views.append(
                {
                    "view_id": view_id,
                    "window_signature": {
                        "title_contains": state.get("title") or title,
                        "screenshot_size": {"width": width, "height": height},
                        "capture_origin_x": origin_x,
                        "capture_origin_y": origin_y,
                        "capture_mode": str(metadata.get("capture_mode") or "window"),
                        "capture_screen_origin_x": metadata.get("origin_x"),
                        "capture_screen_origin_y": metadata.get("origin_y"),
                        "capture_windows": state.get("capture_windows") or [],
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

    @staticmethod
    def _legacy_capture_origin(metadata: dict) -> tuple[int | None, int | None]:
        """返回兼容旧运行逻辑的截图原点偏移。"""

        if metadata.get("capture_mode") == "screen_canvas":
            return 0, 0
        return metadata.get("offset_x"), metadata.get("offset_y")

    def _selected_capture_windows(self) -> list[dict]:
        """返回当前截图参与窗口的轻量元数据。"""

        selected = set(self._checked_window_hwnds())
        if not selected and self._selected_hwnd is not None:
            selected = {self._selected_hwnd}
        windows = []
        for data in self._windows_data:
            hwnd = data.get("hwnd")
            if hwnd not in selected:
                continue
            windows.append(
                {
                    "title": data.get("title"),
                    "hwnd": hwnd,
                    "width": data.get("width"),
                    "height": data.get("height"),
                }
            )
        return windows

    @staticmethod
    def _metadata_from_signature(signature: object | None) -> dict:
        """从窗口签名还原页面使用的截图元数据。"""

        if signature is None:
            return {}
        return {
            "capture_mode": getattr(signature, "capture_mode", "window") or "window",
            "origin_x": getattr(signature, "capture_screen_origin_x", None),
            "origin_y": getattr(signature, "capture_screen_origin_y", None),
            "offset_x": getattr(signature, "capture_origin_x", 0) or 0,
            "offset_y": getattr(signature, "capture_origin_y", 0) or 0,
            "width": getattr(signature, "capture_width", None),
            "height": getattr(signature, "capture_height", None),
        }

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
                "capture_metadata": self._metadata_from_signature(
                    view.window_signature,
                ),
                "capture_windows": (
                    getattr(view.window_signature, "capture_windows", [])
                    if view.window_signature is not None
                    else []
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
                "capture_metadata": self._metadata_from_signature(
                    profile.window_signature,
                ),
                "capture_windows": getattr(
                    profile.window_signature,
                    "capture_windows",
                    [],
                ),
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
        self._latest_capture_metadata = {}
        self._current_view_id = DEFAULT_VIEW_ID
        self._view_states = {
            DEFAULT_VIEW_ID: {
                "title": "",
                "capture": None,
                "anchors": [],
                "capture_width": None,
                "capture_height": None,
                "capture_metadata": {},
                "capture_windows": [],
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
