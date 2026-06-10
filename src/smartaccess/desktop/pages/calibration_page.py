"""Device onboarding and calibration page."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
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
from smartaccess.desktop.widgets.cards import Card, hint_label, page_header, section_title
from smartaccess.desktop.widgets.roi_canvas import RoiCanvas

_ALL_ACTIONS = [
    ("click", "单击", "在锚点中心点击一次。"),
    ("double_click", "双击", "在锚点中心快速双击。"),
    ("type", "输入文字", "先聚焦目标，再输入 value。"),
    ("press_enter", "按回车", "向当前焦点发送 Enter。"),
    ("hotkey", "快捷键", "发送组合键，如 ctrl+s、ctrl+a。"),
    ("wait", "固定等待", "按秒等待固定时长。"),
    ("wait_until", "等待条件", "轮询观测源直到条件满足。"),
    ("screenshot_check", "截图校验", "截图一次并判断识别条件是否成立。"),
]
_DEFAULT_ACTIONS = {"click", "type", "press_enter", "hotkey", "wait_until"}
_ANCHOR_TYPES = [
    ("action_target", "动作目标：要被点击或输入的控件。"),
    ("observation", "观测区：只读，不操作。"),
    ("button", "按钮：强调可点击。"),
    ("input", "输入框：强调可输入。"),
    ("readout", "读数区：读取文本或数值。"),
    ("status", "状态区：读取运行状态、提示信息。"),
    ("region", "通用区域：用于截图比对或模板匹配。"),
]
_VISION_MODES = [
    ("none", "不识别：仅用于动作，不做读值。"),
    ("ocr", "OCR：读取区域内文字或数字。"),
    ("template", "Template：与预存模板图比较。"),
    ("presence", "Presence：判断控件/区域是否出现。"),
    ("color", "Color：判断区域颜色状态。"),
]
_ANCHOR_TYPE_KEYS = [key for key, _ in _ANCHOR_TYPES]
_VISION_MODE_KEYS = [key for key, _ in _VISION_MODES]
_DELETE_GLYPH = "×"
_DEFAULT_VISION_CONFIG = {
    "template_threshold": 0.8,
    "color_tolerance": 0.1,
    "presence_threshold": 0.05,
}


class CalibrationPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = CalibrationViewModel(facade, self)
        self._windows_data: list[dict] = []
        self._selected_hwnd: int | None = None
        self._selected_title = ""
        self._capability_confirmed = False
        self._latest_capture_bytes: bytes | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(
            page_header("设备接入与校准", "扫描窗口、捕获截图、标注 ROI、绑定动作与识别配置。"),
            1,
        )
        self._panel_toggle = QPushButton("配置面板")
        self._panel_toggle.setObjectName("Ghost")
        self._panel_toggle.setCheckable(True)
        self._panel_toggle.setChecked(True)
        self._panel_toggle.setToolTip("显示或隐藏右侧配置面板。")
        header_row.addWidget(self._panel_toggle)
        save_btn = QPushButton("生成 instrument_profile.yaml")
        save_btn.clicked.connect(self._save)
        header_row.addWidget(save_btn)
        root.addLayout(header_row)

        self._inner = QMainWindow()
        self._inner.setDockOptions(QMainWindow.DockOption.AnimatedDocks)

        canvas_card = Card(flush=True)
        canvas_card.add(section_title("截图 / ROI 编辑区"))
        canvas_card.add(
            hint_label(
                "在截图上拖动 ROI 矩形标记锚点区域。右键可删除 ROI，Ctrl+滚轮可缩放画布。"
            )
        )
        self._canvas = RoiCanvas()
        self._canvas.roi_deleted.connect(self._on_canvas_roi_deleted)
        canvas_card.add(self._canvas)
        self._inner.setCentralWidget(canvas_card)

        self._config_dock = QDockWidget("配置面板", self._inner)
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
        tabs.addTab(self._build_profile_tab(), "画像")
        tabs.addTab(self._build_anchor_tab(), "锚点")
        tabs.addTab(self._build_safety_tab(), "确认")
        tabs.setMinimumWidth(520)
        self._config_dock.setWidget(tabs)
        self._inner.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._config_dock)
        root.addWidget(self._inner, 1)

        self._panel_toggle.toggled.connect(self._config_dock.setVisible)
        self._config_dock.visibilityChanged.connect(self._panel_toggle.setChecked)

        self._discover()
        self._refresh_instruments()

    def on_show(self) -> None:
        self._refresh_instruments()

    def _build_window_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(section_title("1. 选择目标窗口"))
        self._windows_list = QListWidget()
        self._windows_list.itemSelectionChanged.connect(self._on_window_selected)
        layout.addWidget(self._windows_list, 1)
        row = QHBoxLayout()
        scan_btn = QPushButton("扫描窗口")
        scan_btn.setObjectName("Ghost")
        scan_btn.clicked.connect(self._discover)
        row.addWidget(scan_btn)
        self._capture_btn = QPushButton("捕获窗口截图")
        self._capture_btn.clicked.connect(self._capture)
        self._capture_btn.setEnabled(False)
        row.addWidget(self._capture_btn)
        self._assist_btn = QPushButton("AI 辅助接入")
        self._assist_btn.setObjectName("Ghost")
        self._assist_btn.clicked.connect(self._generate_ai_profile)
        row.addWidget(self._assist_btn)
        layout.addLayout(row)

        layout.addWidget(section_title("已校准设备"))
        layout.addWidget(hint_label("双击可加载配置；右键可删除设备。"))
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
        self._device_id.setPlaceholderText("例如 weixin_01")
        self._device_id.textChanged.connect(self._auto_fill_title)
        self._title = QLineEdit()
        self._title.setPlaceholderText("选中窗口后可自动填入标题关键字")
        form.addRow("设备 ID *", self._device_id)
        form.addRow("窗口标题包含 *", self._title)
        layout.addLayout(form)

        layout.addWidget(section_title("设备能力"))
        layout.addWidget(
            hint_label(
                "这里只声明这类软件真正支持的动作原语；锚点页再把动作原语绑定到具体控件。"
            )
        )
        self._actions: dict[str, QCheckBox] = {}
        for key, label, tip in _ALL_ACTIONS:
            checkbox = QCheckBox(f"{key} - {label}")
            checkbox.setToolTip(tip)
            checkbox.setChecked(key in _DEFAULT_ACTIONS)
            checkbox.toggled.connect(self._invalidate_capability)
            self._actions[key] = checkbox
            layout.addWidget(checkbox)

        layout.addWidget(self._build_capability_confirm())
        layout.addStretch(1)
        return page

    def _build_capability_confirm(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(8)
        inner.addWidget(section_title("能力确认"))
        inner.addWidget(
            hint_label("修改了设备动作能力后，请再次确认。未确认也能保存，但会被标记为未确认配置。")
        )
        self._capability_status = QLabel("● 尚未确认")
        self._capability_status.setStyleSheet(f"color:{t.WARNING};font-weight:600;")
        inner.addWidget(self._capability_status)
        self._confirm_capability_btn = QPushButton("确认设备能力已配置")
        self._confirm_capability_btn.setObjectName("Ghost")
        self._confirm_capability_btn.clicked.connect(self._confirm_capability)
        inner.addWidget(self._confirm_capability_btn)
        return box

    def _build_anchor_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.addWidget(section_title("2. 锚点、ROI 与识别配置"))
        layout.addWidget(
            hint_label(
                "表格只放锚点编辑；说明改成下方 tab。这样上方可编辑区域更大，适合长列表。"
            )
        )
        self._anchor_table = QTableWidget(0, 7)
        self._anchor_table.setHorizontalHeaderLabels(
            ["锚点", "类型", "ROI 坐标", "动作", "识别", "需确认", ""]
        )
        self._anchor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._anchor_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._anchor_table.itemSelectionChanged.connect(self._refresh_selected_anchor_tools)
        self._anchor_table.verticalHeader().setDefaultSectionSize(52)
        header = self._anchor_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._anchor_table.setColumnWidth(1, 150)
        self._anchor_table.setColumnWidth(3, 160)
        self._anchor_table.setColumnWidth(4, 150)
        self._anchor_table.setColumnWidth(5, 78)
        self._anchor_table.setColumnWidth(6, 44)
        self._anchor_table.setMinimumHeight(320)
        self._anchor_table.setToolTip("选中某一行后，可在下方采集模板/颜色基准并调整阈值。")
        layout.addWidget(self._anchor_table, 1)

        row = QHBoxLayout()
        add_btn = QPushButton("+ 添加锚点")
        add_btn.clicked.connect(self._add_anchor)
        row.addWidget(add_btn)
        sync_btn = QPushButton("从画布同步坐标")
        sync_btn.setObjectName("Ghost")
        sync_btn.setToolTip("刷新表格中的像素坐标，保存时会同时写入 normalized ROI。")
        sync_btn.clicked.connect(self._refresh_anchor_coordinates)
        row.addWidget(sync_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(self._build_vision_config_panel())
        layout.addWidget(self._build_anchor_help_tabs())
        layout.addWidget(
            hint_label(
                "同一个控件如果既要被点击又要被识别，建议拆成两行：动作锚点 + 观测锚点。"
            )
        )
        return page

    def _build_vision_config_panel(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(8)
        inner.addWidget(section_title("识别基准"))

        self._vision_anchor_label = QLabel("未选中锚点")
        self._vision_anchor_label.setObjectName("Body")
        inner.addWidget(self._vision_anchor_label)

        action_row = QHBoxLayout()
        self._capture_template_btn = QPushButton("采集模板基准")
        self._capture_template_btn.setObjectName("Ghost")
        self._capture_template_btn.clicked.connect(self._capture_template_baseline)
        action_row.addWidget(self._capture_template_btn)

        self._capture_color_btn = QPushButton("采集颜色基准")
        self._capture_color_btn.setObjectName("Ghost")
        self._capture_color_btn.clicked.connect(self._capture_color_baseline)
        action_row.addWidget(self._capture_color_btn)

        self._clear_vision_btn = QPushButton("清除识别基准")
        self._clear_vision_btn.setObjectName("Ghost")
        self._clear_vision_btn.clicked.connect(self._clear_selected_baseline)
        action_row.addWidget(self._clear_vision_btn)
        action_row.addStretch(1)
        inner.addLayout(action_row)

        form = QFormLayout()
        self._template_threshold = QDoubleSpinBox()
        self._template_threshold.setRange(0.1, 1.0)
        self._template_threshold.setSingleStep(0.05)
        self._template_threshold.setValue(_DEFAULT_VISION_CONFIG["template_threshold"])
        self._template_threshold.valueChanged.connect(self._persist_selected_anchor_config)
        form.addRow("Template 阈值", self._template_threshold)

        self._color_tolerance = QDoubleSpinBox()
        self._color_tolerance.setRange(0.01, 1.0)
        self._color_tolerance.setSingleStep(0.05)
        self._color_tolerance.setValue(_DEFAULT_VISION_CONFIG["color_tolerance"])
        self._color_tolerance.valueChanged.connect(self._persist_selected_anchor_config)
        form.addRow("Color 容差", self._color_tolerance)

        self._presence_threshold = QDoubleSpinBox()
        self._presence_threshold.setRange(0.01, 1.0)
        self._presence_threshold.setSingleStep(0.01)
        self._presence_threshold.setValue(_DEFAULT_VISION_CONFIG["presence_threshold"])
        self._presence_threshold.valueChanged.connect(self._persist_selected_anchor_config)
        form.addRow("Presence 阈值", self._presence_threshold)
        inner.addLayout(form)

        self._vision_summary = hint_label("模板路径、颜色参考和阈值会跟随当前选中锚点保存。")
        inner.addWidget(self._vision_summary)
        return box

    def _build_anchor_help_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setMaximumHeight(192)
        tabs.addTab(self._build_anchor_type_help(), "类型说明")
        tabs.addTab(self._build_vision_help(), "识别说明")
        return tabs

    def _build_anchor_type_help(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(6)
        inner.addWidget(section_title("锚点类型"))
        label = QLabel(self._format_help_columns(_ANCHOR_TYPES))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        inner.addWidget(label)
        inner.addStretch(1)
        return box

    def _build_vision_help(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(6)
        inner.addWidget(section_title("识别方式"))
        vision_items = [
            ("ocr", "读取联系人名、数字、状态文案，常配 wait_until。"),
            ("template", "先采集模板基准，再做图样匹配。"),
            ("color", "先采集颜色基准，再按容差判断匹配。"),
            ("presence", "用前景占比判断 present / missing。"),
        ]
        label = QLabel(self._format_help_columns(vision_items))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        inner.addWidget(label)
        inner.addStretch(1)
        return box

    @staticmethod
    def _format_help_columns(items: list[tuple[str, str]]) -> str:
        midpoint = (len(items) + 1) // 2
        left_items = items[:midpoint]
        right_items = items[midpoint:]
        rows = max(len(left_items), len(right_items))
        html_rows: list[str] = []
        for index in range(rows):
            left_cell = CalibrationPage._format_help_cell(*left_items[index]) if index < len(left_items) else ""
            right_cell = CalibrationPage._format_help_cell(*right_items[index]) if index < len(right_items) else ""
            html_rows.append(
                "<tr>"
                f"<td style='width:50%;vertical-align:top;padding:0 14px 4px 0;'>{left_cell}</td>"
                f"<td style='width:50%;vertical-align:top;padding:0 0 4px 0;'>{right_cell}</td>"
                "</tr>"
            )
        return f"<table style='width:100%;border-collapse:collapse;'>{''.join(html_rows)}</table>"

    @staticmethod
    def _format_help_cell(key: str, desc: str) -> str:
        return (
            "<div style='margin:0;line-height:1.35;'>"
            f"<span style='color:{t.INK};font-weight:600;'>{escape(key)}</span>"
            f"<span style='color:{t.INK_MUTED};'> - {escape(desc)}</span>"
            "</div>"
        )

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.addWidget(section_title("3. 人工确认与安全项"))
        layout.addWidget(
            hint_label("高风险步骤可以在这里声明，运行时会先停下来等待人工确认。")
        )
        self._safety_table = QTableWidget(0, 6)
        self._safety_table.setHorizontalHeaderLabels(
            ["字段/步骤", "显示名称", "类型", "风险", "需确认", ""]
        )
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

    def _discover(self) -> None:
        self._windows_list.clear()
        self._windows_data.clear()
        try:
            windows = self._vm.discover_windows()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "扫描失败", f"扫描窗口时发生异常：{exc}")
            return
        for window in windows:
            self._windows_data.append(
                {
                    "title": window.title,
                    "hwnd": window.hwnd,
                    "w": window.width,
                    "h": window.height,
                }
            )
            self._windows_list.addItem(f"{window.title}  ({window.width}x{window.height})")
        if not windows:
            self._windows_list.addItem("未发现可用窗口，请确认目标软件已打开。")

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
            QMessageBox.warning(self, "未选择窗口", "请先在窗口列表中选中一个窗口。")
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
        self._latest_capture_bytes = data
        self._canvas.load_image(data)
        self._refresh_anchor_coordinates()

    def _generate_ai_profile(self) -> None:
        prompt, ok = QInputDialog.getMultiLineText(
            self,
            "AI 辅助接入",
            "描述目标软件、需要操作的控件和需要读取的状态：",
            "请根据当前窗口和已有 ROI，生成设备画像草稿。",
        )
        if not ok or not prompt.strip():
            return
        width, height = self._canvas.source_size()
        context = {
            "device_id": self._device_id.text().strip() or "new_device",
            "title_contains": self._title.text().strip() or self._selected_title,
            "window_title": self._selected_title,
            "capture_width": width,
            "capture_height": height,
            "actions": [key for key, checkbox in self._actions.items() if checkbox.isChecked()],
            "anchors": self._collect_anchors(),
        }
        try:
            profile = self._vm.generate_profile_suggestion(prompt.strip(), context)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "生成失败",
                f"AI 助手暂时无法生成接入建议：{exc}\n\n请检查模型配置，或继续手动校准。",
            )
            return
        reasoning = self._vm.profile_suggestion_reasoning()
        summary = (
            f"设备 ID：{profile.device_id}\n"
            f"窗口标题：{profile.window_signature.title_contains or '-'}\n"
            f"建议锚点：{len(profile.anchors)} 个\n\n"
            "是否将建议填入当前页面？填入后仍需人工检查 ROI 和识别配置，再手动保存。"
        )
        if reasoning:
            summary += f"\n\n{reasoning[:800]}"
        reply = QMessageBox.question(
            self,
            "应用接入建议",
            summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_profile_draft(profile)

    def _apply_profile_draft(self, profile) -> None:
        self._device_id.setText(profile.device_id)
        self._title.setText(profile.window_signature.title_contains or "")
        for key, checkbox in self._actions.items():
            checkbox.setChecked(key in profile.actions)
        self._anchor_table.setRowCount(0)
        for anchor in profile.anchors:
            roi = anchor.roi
            if roi and roi.width > 0 and roi.height > 0:
                self._canvas.add_roi(anchor.id, roi.x, roi.y, roi.width, roi.height)
            first_action = anchor.action_bindings[0].action if anchor.action_bindings else "click"
            requires_confirmation = (
                anchor.action_bindings[0].requires_confirmation if anchor.action_bindings else False
            )
            self._insert_anchor_row(
                name=anchor.id,
                roi_name=anchor.id,
                anchor_type=anchor.type,
                action=first_action,
                vision_mode=anchor.vision_mode,
                requires_confirmation=requires_confirmation,
                vision_config=anchor.vision_config.model_dump(mode="json", exclude_none=True)
                if anchor.vision_config
                else None,
            )
        self._capability_confirmed = False
        self._invalidate_capability()
        self._refresh_anchor_coordinates()

    def _confirm_capability(self) -> None:
        selected = [key for key, checkbox in self._actions.items() if checkbox.isChecked()]
        if not selected:
            QMessageBox.warning(self, "未选择能力", "请至少勾选一个设备支持的动作原语。")
            return
        self._capability_confirmed = True
        self._capability_status.setText(f"✓ 已确认：{', '.join(selected)}")
        self._capability_status.setStyleSheet(f"color:{t.SUCCESS};font-weight:600;")

    def _invalidate_capability(self) -> None:
        if self._capability_confirmed:
            self._capability_confirmed = False
            self._capability_status.setText("● 动作能力已修改，请重新确认")
            self._capability_status.setStyleSheet(f"color:{t.WARNING};font-weight:600;")

    def _make_help_combo(self, options: list[tuple[str, str]]) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(34)
        for key, desc in options:
            combo.addItem(key, key)
            combo.setItemData(combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        combo.currentIndexChanged.connect(
            lambda index, box=combo: box.setToolTip(
                box.itemData(index, Qt.ItemDataRole.ToolTipRole) or ""
            )
        )
        combo.setToolTip(options[0][1])
        return combo

    def _add_anchor(self) -> None:
        name, ok = QInputDialog.getText(self, "添加锚点", "锚点名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        self._canvas.add_roi(name)
        self._insert_anchor_row(name=name, roi_name=name)

    def _insert_anchor_row(
        self,
        *,
        name: str,
        roi_name: str,
        anchor_type: str = "action_target",
        action: str = "click",
        vision_mode: str = "none",
        requires_confirmation: bool = False,
        vision_config: dict | None = None,
    ) -> None:
        row = self._anchor_table.rowCount()
        self._anchor_table.insertRow(row)
        name_item = QTableWidgetItem(name)
        name_item.setData(
            Qt.ItemDataRole.UserRole,
            {"vision_config": self._merge_vision_config(vision_config)},
        )
        self._anchor_table.setItem(row, 0, name_item)

        type_box = self._make_help_combo(_ANCHOR_TYPES)
        if anchor_type in _ANCHOR_TYPE_KEYS:
            type_box.setCurrentText(anchor_type)
        self._anchor_table.setCellWidget(row, 1, type_box)

        self._anchor_table.setItem(row, 2, QTableWidgetItem(roi_name))

        action_box = QComboBox()
        action_box.setMinimumHeight(34)
        for key, label, tip in _ALL_ACTIONS:
            action_box.addItem(f"{key} - {label}", key)
            action_box.setItemData(action_box.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        action_box.currentIndexChanged.connect(
            lambda index, box=action_box: box.setToolTip(
                box.itemData(index, Qt.ItemDataRole.ToolTipRole) or ""
            )
        )
        action_index = action_box.findData(action)
        if action_index >= 0:
            action_box.setCurrentIndex(action_index)
        self._anchor_table.setCellWidget(row, 3, action_box)

        vision_box = self._make_help_combo(_VISION_MODES)
        if vision_mode in _VISION_MODE_KEYS:
            vision_box.setCurrentText(vision_mode)
        vision_box.currentIndexChanged.connect(self._refresh_selected_anchor_tools)
        self._anchor_table.setCellWidget(row, 4, vision_box)

        confirm = QCheckBox()
        confirm.setChecked(requires_confirmation)
        self._anchor_table.setCellWidget(row, 5, confirm)

        delete_btn = self._make_delete_button("删除锚点")
        delete_btn.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
        self._anchor_table.setCellWidget(row, 6, delete_btn)
        self._refresh_anchor_coordinates()

    def _delete_anchor(self, row: int) -> None:
        roi_item = self._anchor_table.item(row, 2)
        if roi_item:
            self._canvas.remove_roi(roi_item.text().split("  ")[0].strip())
        self._anchor_table.removeRow(row)
        self._rebind_anchor_delete_buttons()
        self._refresh_selected_anchor_tools()

    def _on_canvas_roi_deleted(self, roi_name: str) -> None:
        for row in range(self._anchor_table.rowCount()):
            item = self._anchor_table.item(row, 2)
            if item and item.text().split("  ")[0].strip() == roi_name:
                self._anchor_table.removeRow(row)
                self._rebind_anchor_delete_buttons()
                self._refresh_selected_anchor_tools()
                return

    def _rebind_anchor_delete_buttons(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            button = self._make_delete_button("删除锚点")
            button.clicked.connect(lambda _checked=False, r=row: self._delete_anchor(r))
            self._anchor_table.setCellWidget(row, 6, button)

    def _refresh_anchor_coordinates(self) -> None:
        for row in range(self._anchor_table.rowCount()):
            roi_item = self._anchor_table.item(row, 2)
            if not roi_item:
                continue
            roi_name = roi_item.text().split("  ")[0].strip()
            rect = self._canvas.roi_rect(roi_name)
            if rect:
                roi_item.setText(
                    f"{roi_name}  ({rect['x']:.0f},{rect['y']:.0f},{rect['width']:.0f},{rect['height']:.0f})"
                )

    def _selected_anchor_row(self) -> int:
        selection = self._anchor_table.selectionModel()
        if selection is None or not selection.hasSelection():
            return -1
        rows = selection.selectedRows()
        return rows[0].row() if rows else -1

    def _refresh_selected_anchor_tools(self) -> None:
        row = self._selected_anchor_row()
        enabled = row >= 0
        for widget in (
            self._capture_template_btn,
            self._capture_color_btn,
            self._clear_vision_btn,
            self._template_threshold,
            self._color_tolerance,
            self._presence_threshold,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self._vision_anchor_label.setText("未选中锚点")
            self._vision_summary.setText("模板路径、颜色参考和阈值会跟随当前选中锚点保存。")
            return

        anchor_name = self._table_text(self._anchor_table, row, 0)
        vision_mode = self._combo_data(self._anchor_table, row, 4)
        config = self._anchor_config_for_row(row)
        self._template_threshold.blockSignals(True)
        self._color_tolerance.blockSignals(True)
        self._presence_threshold.blockSignals(True)
        self._template_threshold.setValue(float(config.get("template_threshold", 0.8)))
        self._color_tolerance.setValue(float(config.get("color_tolerance", 0.1)))
        self._presence_threshold.setValue(float(config.get("presence_threshold", 0.05)))
        self._template_threshold.blockSignals(False)
        self._color_tolerance.blockSignals(False)
        self._presence_threshold.blockSignals(False)

        self._vision_anchor_label.setText(f"当前锚点：{anchor_name}  ·  mode={vision_mode}")
        template_path = config.get("template_asset_path") or "-"
        color_ref = config.get("color_reference_hex") or "-"
        self._vision_summary.setText(
            f"模板：{template_path}\n颜色参考：{color_ref}\n"
            f"Template 阈值={config.get('template_threshold', 0.8):.2f}，"
            f"Color 容差={config.get('color_tolerance', 0.1):.2f}，"
            f"Presence 阈值={config.get('presence_threshold', 0.05):.2f}"
        )

    def _persist_selected_anchor_config(self) -> None:
        row = self._selected_anchor_row()
        if row < 0:
            return
        config = self._anchor_config_for_row(row)
        config["template_threshold"] = self._template_threshold.value()
        config["color_tolerance"] = self._color_tolerance.value()
        config["presence_threshold"] = self._presence_threshold.value()
        self._set_anchor_config_for_row(row, config)
        self._refresh_selected_anchor_tools()

    def _capture_template_baseline(self) -> None:
        row = self._selected_anchor_row()
        cropped = self._crop_selected_anchor_pixmap()
        if row < 0 or cropped is None:
            return
        anchor_name = self._table_text(self._anchor_table, row, 0)
        device_id = self._device_id.text().strip() or "unsaved_device"
        asset_dir = self._vision_asset_dir(device_id)
        asset_dir.mkdir(parents=True, exist_ok=True)
        relative = Path("instruments") / self._safe_name(device_id) / "vision" / f"{self._safe_name(anchor_name)}_template.png"
        absolute = self._vm.workspace_dir() / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        if not cropped.save(str(absolute), "PNG"):
            QMessageBox.warning(self, "采集失败", "模板图片保存失败。")
            return
        config = self._anchor_config_for_row(row)
        config["template_asset_path"] = relative.as_posix()
        self._set_anchor_config_for_row(row, config)
        self._set_selected_vision_mode("template")
        self._refresh_selected_anchor_tools()

    def _capture_color_baseline(self) -> None:
        row = self._selected_anchor_row()
        cropped = self._crop_selected_anchor_pixmap()
        if row < 0 or cropped is None:
            return
        color_hex = self._average_color_hex(cropped)
        config = self._anchor_config_for_row(row)
        config["color_reference_hex"] = color_hex
        self._set_anchor_config_for_row(row, config)
        self._set_selected_vision_mode("color")
        self._refresh_selected_anchor_tools()

    def _clear_selected_baseline(self) -> None:
        row = self._selected_anchor_row()
        if row < 0:
            return
        config = self._anchor_config_for_row(row)
        config.pop("template_asset_path", None)
        config.pop("color_reference_hex", None)
        self._set_anchor_config_for_row(row, config)
        self._refresh_selected_anchor_tools()

    def _crop_selected_anchor_pixmap(self) -> QPixmap | None:
        if not self._latest_capture_bytes:
            QMessageBox.warning(self, "缺少截图", "请先捕获窗口截图，再采集识别基准。")
            return None
        row = self._selected_anchor_row()
        if row < 0:
            QMessageBox.warning(self, "未选中锚点", "请先在表格中选中一个锚点。")
            return None
        roi_name = self._table_text(self._anchor_table, row, 2).split("  ")[0].strip()
        rect = self._canvas.roi_rect(roi_name)
        if not rect:
            QMessageBox.warning(self, "缺少 ROI", "当前锚点没有有效 ROI。")
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._latest_capture_bytes):
            QMessageBox.warning(self, "截图无效", "无法解析当前截图。")
            return None
        return pixmap.copy(
            int(rect["x"]),
            int(rect["y"]),
            int(rect["width"]),
            int(rect["height"]),
        )

    def _average_color_hex(self, pixmap: QPixmap) -> str:
        image = pixmap.toImage()
        width = image.width()
        height = image.height()
        if width <= 0 or height <= 0:
            return "#000000"
        total_r = total_g = total_b = 0
        total = width * height
        for x in range(width):
            for y in range(height):
                color = image.pixelColor(x, y)
                total_r += color.red()
                total_g += color.green()
                total_b += color.blue()
        return "#{:02X}{:02X}{:02X}".format(
            int(total_r / total),
            int(total_g / total),
            int(total_b / total),
        )

    def _anchor_config_for_row(self, row: int) -> dict:
        item = self._anchor_table.item(row, 0)
        stored = item.data(Qt.ItemDataRole.UserRole) if item else None
        stored_config = {}
        if isinstance(stored, dict):
            stored_config = dict(stored.get("vision_config") or {})
        return self._merge_vision_config(stored_config)

    def _set_anchor_config_for_row(self, row: int, config: dict) -> None:
        item = self._anchor_table.item(row, 0)
        if item is None:
            return
        item.setData(
            Qt.ItemDataRole.UserRole,
            {"vision_config": self._merge_vision_config(config)},
        )

    @staticmethod
    def _merge_vision_config(config: dict | None) -> dict:
        merged = dict(_DEFAULT_VISION_CONFIG)
        if config:
            merged.update({key: value for key, value in config.items() if value not in (None, "")})
        return merged

    def _set_selected_vision_mode(self, mode: str) -> None:
        row = self._selected_anchor_row()
        if row < 0:
            return
        combo = self._anchor_table.cellWidget(row, 4)
        if isinstance(combo, QComboBox):
            index = combo.findText(mode)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _vision_asset_dir(self, device_id: str) -> Path:
        return self._vm.workspace_dir() / "instruments" / self._safe_name(device_id) / "vision"

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\\\|?*]+', "_", value.strip())
        return cleaned or "item"

    def _collect_anchors(self) -> list[dict]:
        anchors: list[dict] = []
        for row in range(self._anchor_table.rowCount()):
            name = self._table_text(self._anchor_table, row, 0)
            roi_name = self._table_text(self._anchor_table, row, 2).split("  ")[0].strip()
            rect = self._canvas.roi_rect(roi_name)
            norm = self._canvas.normalized_roi_rect(roi_name)
            type_value = self._combo_data(self._anchor_table, row, 1) or "action_target"
            action_value = self._combo_data(self._anchor_table, row, 3) or "click"
            vision_mode = self._combo_data(self._anchor_table, row, 4) or "none"
            confirm = self._checkbox_value(self._anchor_table, row, 5)
            config = self._anchor_config_for_row(row)
            if not name or not rect:
                continue
            anchors.append(
                {
                    "id": name,
                    "type": type_value,
                    "locator_hint": roi_name,
                    "roi": rect,
                    "normalized_roi": norm,
                    "action_bindings": [
                        {
                            "action": action_value,
                            "requires_confirmation": confirm,
                        }
                    ],
                    "vision_mode": vision_mode,
                    "confidence_threshold": 0.7,
                    "vision_config": config if config else None,
                }
            )
        return anchors

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
        delete_btn = self._make_delete_button("删除确认项")
        delete_btn.clicked.connect(lambda _checked=False, r=row: self._delete_safety_row(r))
        self._safety_table.setCellWidget(row, 5, delete_btn)

    def _delete_safety_row(self, row: int) -> None:
        self._safety_table.removeRow(row)
        self._rebind_safety_delete_buttons()

    def _rebind_safety_delete_buttons(self) -> None:
        for row in range(self._safety_table.rowCount()):
            button = self._make_delete_button("删除确认项")
            button.clicked.connect(lambda _checked=False, r=row: self._delete_safety_row(r))
            self._safety_table.setCellWidget(row, 5, button)

    def _collect_safety_fields(self, anchors: list[dict]) -> tuple[list[dict], list[str]]:
        fields: list[dict] = []
        confirm_steps: list[str] = []
        for anchor in anchors:
            for binding in anchor.get("action_bindings", []):
                if binding.get("requires_confirmation"):
                    confirm_steps.append(anchor["id"])
        for row in range(self._safety_table.rowCount()):
            field_id = self._table_text(self._safety_table, row, 0)
            label = self._table_text(self._safety_table, row, 1) or field_id
            if not field_id:
                continue
            field_type = self._combo_text(self._safety_table, row, 2) or "string"
            risk_level = self._combo_text(self._safety_table, row, 3) or "medium"
            requires_confirmation = self._checkbox_value(self._safety_table, row, 4)
            if requires_confirmation:
                confirm_steps.append(field_id)
            fields.append(
                {
                    "field_id": field_id,
                    "label": label,
                    "value_type": field_type,
                    "risk_level": risk_level,
                    "requires_confirmation": requires_confirmation,
                    "applies_to_steps": [field_id],
                }
            )
        return fields, sorted(set(confirm_steps))

    def _save(self) -> None:
        device_id = self._device_id.text().strip()
        title = self._title.text().strip()
        if not device_id:
            QMessageBox.warning(self, "缺少设备 ID", "请输入设备标识。")
            return
        if not title:
            QMessageBox.warning(self, "缺少窗口标题", "请输入或选择窗口标题关键字。")
            return
        anchors = self._collect_anchors()
        if not anchors:
            QMessageBox.warning(self, "缺少锚点", "请至少添加一个锚点并保存 ROI 坐标。")
            return
        actions = [key for key, checkbox in self._actions.items() if checkbox.isChecked()] or list(_DEFAULT_ACTIONS)
        if not self._capability_confirmed:
            reply = QMessageBox.question(
                self,
                "能力尚未确认",
                "设备能力还没有点击确认，仍然继续保存吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        safety_fields, confirm_steps = self._collect_safety_fields(anchors)
        width, height = self._canvas.source_size()
        try:
            profile = self._vm.create_profile(
                device_id=device_id,
                title_contains=title,
                anchors=anchors,
                actions=actions,
                safety_fields=safety_fields,
                confirm_steps=confirm_steps,
                capture_width=width,
                capture_height=height,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._refresh_instruments()
        suffix = "" if self._capability_confirmed else "\n（注意：本次保存未进行能力确认）"
        QMessageBox.information(
            self,
            "校准完成",
            f"已生成设备画像 {profile.device_id}\n锚点数：{len(profile.anchors)}{suffix}",
        )

    def _refresh_instruments(self) -> None:
        self._instruments.clear()
        for profile in self._vm.list_instruments():
            item = QListWidgetItem(
                f"{profile.device_id}  ·  锚点 {len(profile.anchors)}  ·  动作 {', '.join(profile.actions)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, profile.device_id)
            self._instruments.addItem(item)
        if self._instruments.count() == 0:
            self._instruments.addItem("暂无已校准设备。")

    def _load_instrument(self, item: QListWidgetItem) -> None:
        device_id = item.data(Qt.ItemDataRole.UserRole)
        if not device_id:
            return
        profile = self._vm.get_instrument(device_id)
        if not profile:
            QMessageBox.warning(self, "加载失败", f"无法加载设备配置：{device_id}")
            return

        self._canvas.clear_all()
        self._anchor_table.setRowCount(0)
        self._safety_table.setRowCount(0)

        self._device_id.setText(profile.device_id)
        self._title.setText(profile.window_signature.title_contains or "")
        for key, checkbox in self._actions.items():
            checkbox.setChecked(key in profile.actions)

        self._capability_confirmed = True
        self._capability_status.setText(f"✓ 已确认：{', '.join(profile.actions)}")
        self._capability_status.setStyleSheet(f"color:{t.SUCCESS};font-weight:600;")

        for anchor in profile.anchors:
            if anchor.roi:
                self._canvas.add_roi(
                    anchor.id,
                    anchor.roi.x,
                    anchor.roi.y,
                    anchor.roi.width,
                    anchor.roi.height,
                )
            first_action = anchor.action_bindings[0].action if anchor.action_bindings else "click"
            requires_confirmation = (
                anchor.action_bindings[0].requires_confirmation if anchor.action_bindings else False
            )
            self._insert_anchor_row(
                name=anchor.id,
                roi_name=anchor.id,
                anchor_type=anchor.type,
                action=first_action,
                vision_mode=anchor.vision_mode,
                requires_confirmation=requires_confirmation,
                vision_config=anchor.vision_config.model_dump(mode="json", exclude_none=True)
                if anchor.vision_config
                else None,
            )

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
            confirm = QCheckBox()
            confirm.setChecked(field.requires_confirmation or False)
            self._safety_table.setCellWidget(row, 4, confirm)
            delete_btn = self._make_delete_button("删除确认项")
            delete_btn.clicked.connect(lambda _checked=False, r=row: self._delete_safety_row(r))
            self._safety_table.setCellWidget(row, 5, delete_btn)

        self._rebind_anchor_delete_buttons()
        self._rebind_safety_delete_buttons()
        self._refresh_anchor_coordinates()
        self._refresh_selected_anchor_tools()
        QMessageBox.information(
            self,
            "配置已加载",
            f"已加载设备 {profile.device_id} 的配置，可继续调整并重新保存。",
        )

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
        delete_action = menu.addAction("删除设备")
        action = menu.exec(self._instruments.mapToGlobal(pos))
        if action == load_action:
            self._load_instrument(item)
        elif action == delete_action:
            self._delete_instrument(device_id)

    def _delete_instrument(self, device_id: str) -> None:
        try:
            refs = self._vm.check_references(device_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "引用检查失败", str(exc))
            return

        if refs.active_session_count > 0:
            QMessageBox.warning(
                self,
                "无法删除",
                f"设备 {device_id} 正被 {refs.active_session_count} 个运行中的 session 使用。",
            )
            return

        parts = [f"即将删除设备 {device_id}。"]
        if refs.draft_count > 0:
            parts.append(f"被 {refs.draft_count} 个草稿引用：{', '.join(refs.referencing_workflow_ids or [])}")
        if refs.local_template_count > 0:
            parts.append(
                f"被 {refs.local_template_count} 个本地模板引用：{', '.join(refs.referencing_template_ids or [])}"
            )
        if refs.draft_count > 0 or refs.local_template_count > 0:
            parts.append("删除后相关工作流会显示缺少设备，需要重新校准后修复。")

        reply = QMessageBox.question(
            self,
            "确认删除设备",
            "\n".join(parts),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._vm.delete_instrument(device_id, force=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self._refresh_instruments()
        QMessageBox.information(self, "已删除", f"设备 {device_id} 已删除。")

    @staticmethod
    def _make_delete_button(tooltip: str) -> QPushButton:
        button = QPushButton(_DELETE_GLYPH)
        button.setObjectName("Danger")
        button.setToolTip(tooltip)
        button.setFixedSize(32, 30)
        return button

    @staticmethod
    def _table_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item else ""

    @staticmethod
    def _combo_text(table: QTableWidget, row: int, column: int) -> str:
        widget = table.cellWidget(row, column)
        return widget.currentText().strip() if isinstance(widget, QComboBox) else ""

    @staticmethod
    def _combo_data(table: QTableWidget, row: int, column: int) -> str:
        widget = table.cellWidget(row, column)
        return widget.currentData() if isinstance(widget, QComboBox) else ""

    @staticmethod
    def _checkbox_value(table: QTableWidget, row: int, column: int) -> bool:
        widget = table.cellWidget(row, column)
        return widget.isChecked() if isinstance(widget, QCheckBox) else False
