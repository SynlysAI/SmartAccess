"""Device onboarding & calibration page.

Layout is a nested :class:`QMainWindow`: the ROI canvas occupies the full center
so it can be enlarged, while the configuration panel (窗口 / 属性 / 锚点 / 确认)
lives in a dockable side panel that can be hidden, floated, or pinned back.

Produces a complete ``instrument_profile.yaml``: window discovery, screenshot
capture, coordinate-aware ROI annotation, anchor/action binding, instrument-level
capability confirmation, and generic safety fields.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t
from smartaccess.desktop.viewmodels.calibration_vm import CalibrationViewModel
from smartaccess.desktop.widgets.cards import Card, hint_label, section_title
from smartaccess.desktop.widgets.roi_canvas import RoiCanvas

_ALL_ACTIONS = [
    ("click", "单击", "在锚点中心点击鼠标左键"),
    ("double_click", "双击", "在锚点中心双击鼠标左键"),
    ("type", "输入文字", "点击锚点后键入文本（取动作的 value）"),
    ("press_enter", "按回车键", "在输入框中按回车键确认输入"),
    ("hotkey", "快捷键", "发送组合键，如 ctrl+s、enter"),
    ("wait", "等待", "固定等待一段时间"),
    ("wait_until", "等待条件", "轮询观测区直到满足条件"),
    ("screenshot_check", "截图校验", "截图并交由识别模块校验"),
]
_DEFAULT_ACTIONS = {"click", "type", "press_enter", "hotkey", "wait_until"}

# Anchor types — what each anchor represents in the instrument UI.
_ANCHOR_TYPES = [
    ("action_target", "动作目标：会被点击/输入的可操作控件（按钮、输入框）"),
    ("observation", "观测区：仅读取、不操作，交给识别模块取值"),
    ("button", "按钮：action_target 的细分，强调可点击"),
    ("input", "输入框：action_target 的细分，强调可键入"),
    ("readout", "读数区：observation 的细分，数值/文本读数"),
    ("status", "状态区：observation 的细分，运行状态/提示"),
    ("region", "通用区域：截图比对或模板匹配用的范围"),
]
# Vision modes — how the observation region is recognized at runtime.
_VISION_MODES = [
    ("none", "不识别：仅作为动作目标，不读取内容"),
    ("ocr", "OCR 文本识别：读取区域内文字/数字（已接入 stub，可替换 PaddleOCR）"),
    ("template", "模板匹配：与预存图样比对，判断是否出现（规划中）"),
    ("presence", "存在性检测：判断区域是否非空/有控件（已接入 stub）"),
    ("color", "颜色识别：按主色判断状态，如红=停止/绿=运行（规划中）"),
]
_ANCHOR_TYPE_KEYS = [k for k, _ in _ANCHOR_TYPES]
_VISION_MODE_KEYS = [k for k, _ in _VISION_MODES]
_DELETE_GLYPH = "×"


class CalibrationPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = CalibrationViewModel(facade, self)
        self._windows_data: list[dict] = []
        self._selected_hwnd: int | None = None
        self._selected_title = ""
        self._capability_confirmed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        header_row = QHBoxLayout()
        from smartaccess.desktop.widgets.cards import page_header

        header_row.addWidget(
            page_header("设备接入与校准", "扫描窗口、截图标注、绑定动作、保存真实仪器画像"),
            1,
        )
        self._panel_toggle = QPushButton("◧ 配置面板")
        self._panel_toggle.setObjectName("Ghost")
        self._panel_toggle.setCheckable(True)
        self._panel_toggle.setChecked(True)
        self._panel_toggle.setToolTip("显示/隐藏右侧配置面板，隐藏后 ROI 编辑区可放大")
        header_row.addWidget(self._panel_toggle)
        save_btn = QPushButton("生成 instrument_profile.yaml")
        save_btn.clicked.connect(self._save)
        header_row.addWidget(save_btn)
        root.addLayout(header_row)

        # Nested QMainWindow: canvas central, config as a dockable panel.
        self._inner = QMainWindow()
        self._inner.setDockOptions(QMainWindow.DockOption.AnimatedDocks)

        canvas_card = Card(flush=True)
        canvas_card.add(section_title("截图 / ROI 编辑区"))
        canvas_card.add(
            hint_label("在截图上拖动 ROI 矩形标记锚点区域，拖动四角可缩放大小。"
                       "Ctrl+滚轮缩放画面，右键删除 ROI。")
        )
        self._canvas = RoiCanvas()
        self._canvas.roi_deleted.connect(self._on_canvas_roi_deleted)
        canvas_card.add(self._canvas)
        self._inner.setCentralWidget(canvas_card)

        self._config_dock = QDockWidget("配置面板", self._inner)
        self._config_dock.setObjectName("CalibConfigDock")
        self._config_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._config_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        tabs = QTabWidget()
        tabs.addTab(self._build_window_tab(), "窗口")
        tabs.addTab(self._build_profile_tab(), "属性")
        tabs.addTab(self._build_anchor_tab(), "锚点")
        tabs.addTab(self._build_safety_tab(), "确认")
        tabs.setMinimumWidth(420)
        self._config_dock.setWidget(tabs)
        self._inner.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._config_dock)
        root.addWidget(self._inner, 1)

        self._panel_toggle.toggled.connect(self._config_dock.setVisible)
        self._config_dock.visibilityChanged.connect(self._panel_toggle.setChecked)

        self._discover()
        self._refresh_instruments()

    def on_show(self) -> None:
        """Refresh the calibrated-instrument list when the page is shown."""

        self._refresh_instruments()

    def _build_window_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(section_title("① 选择仪器窗口"))
        self._windows_list = QListWidget()
        self._windows_list.itemSelectionChanged.connect(self._on_window_selected)
        layout.addWidget(self._windows_list, 1)
        row = QHBoxLayout()
        scan_btn = QPushButton("扫描窗口")
        scan_btn.setObjectName("Ghost")
        scan_btn.clicked.connect(self._discover)
        row.addWidget(scan_btn)
        self._capture_btn = QPushButton("捕获窗口画面")
        self._capture_btn.clicked.connect(self._capture)
        self._capture_btn.setEnabled(False)
        row.addWidget(self._capture_btn)
        layout.addLayout(row)
        layout.addWidget(section_title("已校准仪器"))
        layout.addWidget(hint_label("双击可加载配置；右键可删除仪器"))
        self._instruments = QListWidget()
        self._instruments.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._instruments.customContextMenuRequested.connect(self._on_instruments_context_menu)
        self._instruments.itemDoubleClicked.connect(self._load_instrument)
        layout.addWidget(self._instruments)
        return page

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        form = QFormLayout()
        self._device_id = QLineEdit()
        self._device_id.setPlaceholderText("输入设备标识，如 instrument_win_01")
        self._device_id.textChanged.connect(self._auto_fill_title)
        self._title = QLineEdit()
        self._title.setPlaceholderText("选中窗口后自动填入标题")
        form.addRow("设备 ID *", self._device_id)
        form.addRow("窗口标题包含 *", self._title)
        layout.addLayout(form)

        layout.addWidget(section_title("仪器级能力（IO / 动作原语）"))
        layout.addWidget(
            hint_label("勾选该仪器上位机真正支持的操作原语。这是设备层面的能力声明，"
                       "运行时执行器只会调用这里声明过的动作；锚点上的「动作」则是把"
                       "某个能力具体绑定到某个控件。")
        )
        self._actions: dict[str, QCheckBox] = {}
        for key, label, tip in _ALL_ACTIONS:
            cb = QCheckBox(f"{key} — {label}")
            cb.setToolTip(tip)
            cb.setChecked(key in _DEFAULT_ACTIONS)
            cb.toggled.connect(self._invalidate_capability)
            self._actions[key] = cb
            layout.addWidget(cb)

        layout.addWidget(self._build_capability_confirm())
        layout.addStretch(1)
        return page

    def _build_capability_confirm(self) -> QWidget:
        """The 'confirm instrument IO / capability is configured' control (item 6)."""

        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(8)
        inner.addWidget(section_title("能力确认"))
        inner.addWidget(
            hint_label("确认上方仪器 IO / 动作能力已配置正确后再生成画像。"
                       "未确认时仍可保存，但会在审计中标记为「能力未经确认」。")
        )
        self._capability_status = QLabel("● 能力尚未确认")
        self._capability_status.setStyleSheet(f"color:{t.WARNING};font-weight:600;")
        inner.addWidget(self._capability_status)
        self._confirm_capability_btn = QPushButton("确认仪器 IO / 能力已配置")
        self._confirm_capability_btn.setObjectName("Ghost")
        self._confirm_capability_btn.clicked.connect(self._confirm_capability)
        inner.addWidget(self._confirm_capability_btn)
        return box

    def _confirm_capability(self) -> None:
        selected = [k for k, cb in self._actions.items() if cb.isChecked()]
        if not selected:
            QMessageBox.warning(self, "未选择能力", "请至少勾选一个仪器支持的动作原语。")
            return
        self._capability_confirmed = True
        self._capability_status.setText(f"✓ 能力已确认：{', '.join(selected)}")
        self._capability_status.setStyleSheet(f"color:{t.SUCCESS};font-weight:600;")

    def _invalidate_capability(self) -> None:
        if self._capability_confirmed:
            self._capability_confirmed = False
            self._capability_status.setText("● 能力已修改，请重新确认")
            self._capability_status.setStyleSheet(f"color:{t.WARNING};font-weight:600;")

    def _build_anchor_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.addWidget(section_title("③ 锚点、ROI 与动作绑定"))
        layout.addWidget(
            hint_label("每个锚点 = 仪器界面上的一块区域 + 它的用途。"
                       "「类型」说明这块区域是什么（动作目标还是观测区，将鼠标悬停查看说明），"
                       "「动作」把仪器能力绑定到这个锚点，「识别」说明运行时如何读取这块区域。")
        )
        self._anchor_table = QTableWidget(0, 7)
        self._anchor_table.setHorizontalHeaderLabels(
            ["锚点", "类型 ⓘ", "ROI 坐标", "动作", "识别 ⓘ", "需确认", ""]
        )
        self._anchor_table.verticalHeader().setDefaultSectionSize(48)
        header = self._anchor_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._anchor_table.setColumnWidth(1, 148)
        self._anchor_table.setColumnWidth(3, 168)
        self._anchor_table.setColumnWidth(4, 148)
        self._anchor_table.setColumnWidth(5, 78)
        self._anchor_table.setColumnWidth(6, 44)
        self._anchor_table.setToolTip(
            "类型/识别列的下拉项均有说明，选择后将鼠标悬停在单元格上查看含义。"
        )
        layout.addWidget(self._anchor_table, 1)

        # Help block explaining anchor types and vision modes (items 7 & 8).
        layout.addWidget(self._build_anchor_help())

        # Feedback guidance: how to use OCR / template / color
        layout.addWidget(self._build_vision_guidance())

        row = QHBoxLayout()
        add_btn = QPushButton("+ 添加锚点")
        add_btn.clicked.connect(self._add_anchor)
        row.addWidget(add_btn)
        sync_btn = QPushButton("从画布同步坐标")
        sync_btn.setObjectName("Ghost")
        sync_btn.setToolTip(
            "把画布上每个 ROI 当前的像素坐标 (x,y,宽,高) 回填到「ROI 坐标」列。"
            "拖动或缩放 ROI 后点此刷新，保存时即以此坐标写入画像。"
        )
        sync_btn.clicked.connect(self._refresh_anchor_coordinates)
        row.addWidget(sync_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(
            hint_label("「动作」绑定的是仪器能力，因此无需再单独配置仪器层面的动作——"
                       "锚点动作 = 把已声明的仪器能力指向具体控件。观测类锚点可不绑定动作。")
        )
        return page

    def _build_anchor_help(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(4)
        inner.addWidget(section_title("类型与识别说明"))
        type_lines = "<br>".join(
            f"<span style='color:{t.INK};font-weight:600;'>{k}</span>"
            f"<span style='color:{t.INK_MUTED};'> — {desc.split('：',1)[-1]}</span>"
            for k, desc in _ANCHOR_TYPES
        )
        vision_lines = "<br>".join(
            f"<span style='color:{t.INK};font-weight:600;'>{k}</span>"
            f"<span style='color:{t.INK_MUTED};'> — {desc.split('：',1)[-1]}</span>"
            for k, desc in _VISION_MODES
        )
        lbl_type = QLabel(f"<b style='color:{t.INK_SUBTLE};'>锚点类型</b><br>{type_lines}")
        lbl_type.setTextFormat(Qt.TextFormat.RichText)
        lbl_type.setWordWrap(True)
        lbl_vision = QLabel(f"<b style='color:{t.INK_SUBTLE};'>识别方式</b><br>{vision_lines}")
        lbl_vision.setTextFormat(Qt.TextFormat.RichText)
        lbl_vision.setWordWrap(True)
        inner.addWidget(lbl_type)
        inner.addWidget(lbl_vision)
        return box

    def _build_vision_guidance(self) -> QWidget:
        """How to use OCR / template / color — friendly guidance next to the table."""
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(4)
        inner.addWidget(section_title("🔍 如何使用 OCR / Template / Color / Presence"))
        tips = (
            "<ul style='margin:4px 0;color:%s;'>"
            "<li><b>OCR 文本识别</b> — 适用于读数区、状态文字。运行时用 PaddleOCR 读取 ROI 内文字，"
            "可用于 <code>wait_until</code> 等待特定文字出现。</li>"
            "<li><b>Template 模板匹配</b> — 适用于图标/按钮。先点击「采集模板基准」保存当前 ROI 截图，"
            "运行时用 OpenCV matchTemplate 比对相似度。相似度 ≥ 阈值视为匹配成功。</li>"
            "<li><b>Color 颜色识别</b> — 适用于状态指示灯。先点击「采集颜色基准」记录参考色，"
            "运行时采样 ROI 主色并与参考色比较 HSV 距离。距离 ≤ 容差视为匹配。</li>"
            "<li><b>Presence 存在性检测</b> — 适用于判断控件/窗口是否出现。"
            "计算 ROI 前景像素占比，超过阈值视为存在。</li>"
            "</ul>"
        ) % t.INK_MUTED
        lbl = QLabel(tips)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        inner.addWidget(lbl)
        return box

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.addWidget(section_title("需人工确认的步骤 / 通用安全字段"))
        layout.addWidget(
            hint_label("高风险步骤（如启动运行、超量程参数）在此声明后，运行时会暂停并"
                       "要求人工确认，确保危险动作不会被自动跳过。")
        )
        self._safety_table = QTableWidget(0, 6)
        self._safety_table.setHorizontalHeaderLabels(["字段/步骤", "显示名称", "类型", "风险", "需确认", ""])
        self._safety_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._safety_table.setColumnWidth(5, 44)
        layout.addWidget(self._safety_table, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("+ 添加确认项")
        add_btn.setObjectName("Ghost")
        add_btn.clicked.connect(self._add_safety_field)
        row.addWidget(add_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    # ------------------------------------------------------------------ #
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
        self._canvas.add_roi(name)
        self._insert_anchor_row(name=name, roi_name=name)

    def _insert_anchor_row(self, *, name: str, roi_name: str) -> None:
        row = self._anchor_table.rowCount()
        self._anchor_table.insertRow(row)
        self._anchor_table.setItem(row, 0, QTableWidgetItem(name))
        type_box = self._make_help_combo(_ANCHOR_TYPES)
        self._anchor_table.setCellWidget(row, 1, type_box)
        self._anchor_table.setItem(row, 2, QTableWidgetItem(roi_name))
        action_box = QComboBox()
        action_box.setMinimumHeight(34)
        for key, label, tip in _ALL_ACTIONS:
            action_box.addItem(f"{key} · {label}", key)
            action_box.setItemData(action_box.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self._anchor_table.setCellWidget(row, 3, action_box)
        vision_box = self._make_help_combo(_VISION_MODES)
        self._anchor_table.setCellWidget(row, 4, vision_box)
        confirm = QCheckBox()
        self._anchor_table.setCellWidget(row, 5, confirm)
        del_btn = self._make_delete_button("删除锚点")
        del_btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
        self._anchor_table.setCellWidget(row, 6, del_btn)
        self._refresh_anchor_coordinates()

    def _make_help_combo(self, options: list[tuple[str, str]]) -> QComboBox:
        """A combo whose items carry a tooltip and whose current value is its key."""

        box = QComboBox()
        box.setMinimumHeight(34)
        for key, desc in options:
            box.addItem(key, key)
            box.setItemData(box.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        box.setToolTip(options[0][1])
        box.currentIndexChanged.connect(
            lambda idx, b=box: b.setToolTip(b.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "")
        )
        return box

    def _delete_anchor(self, row: int) -> None:
        roi_item = self._anchor_table.item(row, 2)
        if roi_item:
            self._canvas.remove_roi(roi_item.text().split("  ")[0].strip())
        self._anchor_table.removeRow(row)
        self._rebind_delete_buttons()

    def _on_canvas_roi_deleted(self, roi_name: str) -> None:
        for row in range(self._anchor_table.rowCount()):
            item = self._anchor_table.item(row, 2)
            if item and item.text().split("  ")[0].strip() == roi_name:
                self._anchor_table.removeRow(row)
                self._rebind_delete_buttons()
                return

    def _rebind_delete_buttons(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            btn = self._make_delete_button("删除锚点")
            btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
            self._anchor_table.setCellWidget(row, 6, btn)

    @staticmethod
    def _make_delete_button(tooltip: str) -> QPushButton:
        button = QPushButton(_DELETE_GLYPH)
        button.setObjectName("Danger")
        button.setToolTip(tooltip)
        button.setFixedSize(32, 30)
        return button

    def _refresh_anchor_coordinates(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            roi_item = self._anchor_table.item(row, 2)
            if not roi_item:
                continue
            roi_name = roi_item.text().split("  ")[0].strip()
            rect = self._canvas.roi_rect(roi_name)
            if rect:
                roi_item.setText(
                    f"{roi_name}  ({rect['x']:.0f},{rect['y']:.0f},"
                    f"{rect['width']:.0f},{rect['height']:.0f})"
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
        del_btn = self._make_delete_button("删除确认项")
        del_btn.clicked.connect(lambda _checked=False, r=row: self._delete_safety_row(r))
        self._safety_table.setCellWidget(row, 5, del_btn)

    def _delete_safety_row(self, row: int) -> None:
        self._safety_table.removeRow(row)
        self._rebind_safety_delete_buttons()

    def _rebind_safety_delete_buttons(self) -> None:
        for row in range(self._safety_table.rowCount()):
            btn = self._make_delete_button("删除确认项")
            btn.clicked.connect(lambda _checked=False, r=row: self._delete_safety_row(r))
            self._safety_table.setCellWidget(row, 5, btn)

    # ------------------------------------------------------------------ #
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
        if not self._capability_confirmed:
            reply = QMessageBox.question(
                self,
                "能力未确认",
                "仪器 IO / 能力尚未点击确认。仍要继续生成画像吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
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
        suffix = "" if self._capability_confirmed else "\n（注意：能力未经确认）"
        QMessageBox.information(
            self, "校准完成",
            f"已生成仪器画像: {profile.device_id}\n锚点: {len(profile.anchors)} 个{suffix}",
        )

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
            anchor_type = type_box.currentData() if isinstance(type_box, QComboBox) else "action_target"
            action = action_box.currentData() if isinstance(action_box, QComboBox) else "click"
            vision_mode = vision_box.currentData() if isinstance(vision_box, QComboBox) else "none"
            anchors.append(
                {
                    "id": name,
                    "type": anchor_type,
                    "locator_hint": roi_name,
                    "roi": rect,
                    "normalized_roi": norm,
                    "action_bindings": [
                        {
                            "action": action,
                            "requires_confirmation": confirm.isChecked() if isinstance(confirm, QCheckBox) else False,
                        }
                    ],
                    "vision_mode": vision_mode,
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
            item = QListWidgetItem(
                f"{profile.device_id}  ·  锚点 {len(profile.anchors)}  ·  动作 {', '.join(profile.actions)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, profile.device_id)
            self._instruments.addItem(item)
        if self._instruments.count() == 0:
            self._instruments.addItem("尚无已校准仪器")

    def _load_instrument(self, item: QListWidgetItem) -> None:
        """Load an existing instrument profile for editing."""
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return

        profile = self._vm.get_instrument(device_id)
        if not profile:
            QMessageBox.warning(self, "加载失败", f"无法加载设备配置: {device_id}")
            return

        # Clear existing state
        self._canvas.clear_all()
        self._anchor_table.setRowCount(0)
        self._safety_table.setRowCount(0)

        # Load basic info
        self._device_id.setText(profile.device_id)
        self._title.setText(profile.window_signature.title_contains or "")

        # Load actions
        for key, cb in self._actions.items():
            cb.setChecked(key in profile.actions)

        # Mark capability as confirmed since it's from a saved profile
        self._capability_confirmed = True
        self._capability_status.setText(f"✓ 能力已确认：{', '.join(profile.actions)}")
        self._capability_status.setStyleSheet(f"color:{t.SUCCESS};font-weight:600;")

        # Load anchors
        for anchor in profile.anchors:
            row = self._anchor_table.rowCount()
            self._anchor_table.insertRow(row)

            # Anchor ID
            self._anchor_table.setItem(row, 0, QTableWidgetItem(anchor.id))

            # Type
            type_box = self._make_help_combo(_ANCHOR_TYPES)
            if anchor.type in _ANCHOR_TYPE_KEYS:
                type_box.setCurrentText(anchor.type)
            self._anchor_table.setCellWidget(row, 1, type_box)

            # ROI - add to canvas
            if anchor.roi:
                roi_name = anchor.id
                self._canvas.add_roi(
                    roi_name,
                    anchor.roi.x,
                    anchor.roi.y,
                    anchor.roi.width,
                    anchor.roi.height,
                )
                roi_text = f"{roi_name}  ({anchor.roi.x:.0f},{anchor.roi.y:.0f},{anchor.roi.width:.0f},{anchor.roi.height:.0f})"
                self._anchor_table.setItem(row, 2, QTableWidgetItem(roi_text))

            # Action (use first action binding if available)
            action_box = QComboBox()
            action_box.setMinimumHeight(34)
            for key, label, tip in _ALL_ACTIONS:
                action_box.addItem(f"{key} · {label}", key)
                action_box.setItemData(action_box.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            if anchor.action_bindings:
                first_action = anchor.action_bindings[0].action
                for i in range(action_box.count()):
                    if action_box.itemData(i) == first_action:
                        action_box.setCurrentIndex(i)
                        break
            self._anchor_table.setCellWidget(row, 3, action_box)

            # Vision mode
            vision_box = self._make_help_combo(_VISION_MODES)
            if anchor.vision_mode in _VISION_MODE_KEYS:
                vision_box.setCurrentText(anchor.vision_mode)
            self._anchor_table.setCellWidget(row, 4, vision_box)

            # Requires confirmation
            confirm = QCheckBox()
            if anchor.action_bindings:
                confirm.setChecked(anchor.action_bindings[0].requires_confirmation or False)
            self._anchor_table.setCellWidget(row, 5, confirm)

            # Delete button
            del_btn = self._make_delete_button("删除锚点")
            del_btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
            self._anchor_table.setCellWidget(row, 6, del_btn)

        # Rebind delete buttons after loading all anchors
        self._rebind_delete_buttons()

        # Load safety fields
        if profile.safety_limits and profile.safety_limits.fields:
            for field in profile.safety_limits.fields:
                row = self._safety_table.rowCount()
                self._safety_table.insertRow(row)
                self._safety_table.setItem(row, 0, QTableWidgetItem(field.field_id))
                self._safety_table.setItem(row, 1, QTableWidgetItem(field.label or field.field_id))

                type_box = QComboBox()
                type_box.addItems(["string", "number", "bool", "choice"])
                type_box.setCurrentText(field.value_type or "string")
                self._safety_table.setCellWidget(row, 2, type_box)

                risk_box = QComboBox()
                risk_box.addItems(["low", "medium", "high"])
                risk_box.setCurrentText(field.risk_level or "medium")
                self._safety_table.setCellWidget(row, 3, risk_box)

                confirm_cb = QCheckBox()
                confirm_cb.setChecked(field.requires_confirmation or False)
                self._safety_table.setCellWidget(row, 4, confirm_cb)

        QMessageBox.information(
            self,
            "配置已加载",
            f"已加载设备 {profile.device_id} 的配置\n"
            f"- {len(profile.anchors)} 个锚点\n"
            f"- {len(profile.actions)} 个动作\n\n"
            f"你可以在截图上调整锚点位置，修改后点击「生成 instrument_profile.yaml」保存。"
        )

        # Rebind safety delete buttons after loading
        self._rebind_safety_delete_buttons()

    def _on_instruments_context_menu(self, pos) -> None:
        item = self._instruments.itemAt(pos)
        if item is None:
            return
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return
        menu = QMenu(self)
        load_action = menu.addAction("加载配置")
        menu.addSeparator()
        delete_action = menu.addAction("删除仪器")
        action = menu.exec(self._instruments.mapToGlobal(pos))
        if action == load_action:
            self._load_instrument(item)
        elif action == delete_action:
            self._delete_instrument(device_id)

    def _delete_instrument(self, device_id: str) -> None:
        """Delete an instrument profile with reference pre-check."""
        try:
            refs = self._vm.check_references(device_id)
        except Exception as exc:
            QMessageBox.critical(self, "引用检查失败", str(exc))
            return

        # Build warning message
        parts = [f"即将删除仪器「{device_id}」"]
        if refs.active_session_count > 0:
            QMessageBox.warning(
                self, "无法删除",
                f"仪器 {device_id} 正被 {refs.active_session_count} 个运行中 session 使用，无法删除。\n请先停止相关运行。"
            )
            return
        if refs.draft_count > 0:
            wf_list = ", ".join(refs.referencing_workflow_ids or [])
            parts.append(f"⚠ 被 {refs.draft_count} 个本地草稿引用：{wf_list}")
        if refs.local_template_count > 0:
            t_list = ", ".join(refs.referencing_template_ids or [])
            parts.append(f"⚠ 被 {refs.local_template_count} 个本地模板引用：{t_list}")
        if refs.draft_count > 0 or refs.local_template_count > 0:
            parts.append("\n删除后相关工作流将显示「仪器缺失」，可重新校准后修复。不会级联删除工作流或模板。")

        reply = QMessageBox.question(
            self,
            "确认删除仪器",
            "\n".join(parts),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._vm.delete_instrument(device_id, force=True)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return

        self._refresh_instruments()
        QMessageBox.information(self, "已删除", f"仪器 {device_id} 已删除。")
