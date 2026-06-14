"""锚点表格组件。"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from smartaccess_v2.desktop.widgets.table_style import (
    NoWheelComboBox,
    configure_data_table,
    interactive_header,
    set_embedded_editor_height,
)

ACTION_OPTIONS = [
    ("click", "单击"),
    ("type", "输入"),
    ("hotkey", "快捷键"),
    ("press_enter", "回车"),
]


@dataclass(slots=True)
class AnchorRow:
    """锚点表格行模型。"""

    anchor_id: str
    action_roi: str
    action: str = "click"
    ocr_enabled: bool = False
    observe_roi: str = ""
    requires_confirmation: bool = False


class AnchorTable(QTableWidget):
    """用于编辑锚点、动作和 OCR 观察区域的表格。"""

    row_delete_requested = pyqtSignal(int)
    row_ocr_toggled = pyqtSignal(int, bool)
    row_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        """初始化锚点表格。"""

        super().__init__(0, 7, parent)
        self.setHorizontalHeaderLabels(
            ["锚点 ID", "动作区域", "动作", "OCR", "观察区域", "确认", ""]
        )
        configure_data_table(self, row_height=44)
        header = interactive_header(self)
        header.setStretchLastSection(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.setColumnWidth(2, 112)
        self.setColumnWidth(3, 58)
        self.setColumnWidth(4, 150)
        self.setColumnWidth(5, 58)
        self.setColumnWidth(6, 42)
        self.itemChanged.connect(self._on_item_changed)

    def minimumSizeHint(self):
        """返回表格可接受的最小宽度，避免撑大父级窗口。"""

        return QSize(300, 120)

    def sizeHint(self):
        """返回合理默认尺寸，控制表格对布局空间的诉求。"""

        return QSize(520, 220)

    def add_anchor(self, row_data: AnchorRow) -> int:
        """新增锚点行。

        Args:
            row_data: 锚点行模型。

        Returns:
            新增行号。
        """

        row = self.rowCount()
        self.insertRow(row)
        self._set_item(row, 0, row_data.anchor_id)
        self._set_item(row, 1, row_data.action_roi)
        self.setCellWidget(row, 2, self._action_combo(row_data.action))
        self.setCellWidget(row, 3, self._checkbox(row_data.ocr_enabled, "ocr"))
        self._set_item(row, 4, row_data.observe_roi)
        self.setCellWidget(row, 5, self._checkbox(row_data.requires_confirmation, "confirm"))
        delete_btn = QPushButton("×")
        delete_btn.setObjectName("TableDanger")
        delete_btn.setToolTip("删除锚点")
        delete_btn.setFixedSize(28, 28)
        delete_btn.clicked.connect(lambda _checked=False, r=row: self.row_delete_requested.emit(r))
        self.setCellWidget(row, 6, delete_btn)
        self._store_row(row, row_data)
        self.rebind_row_widgets()
        return row

    def set_rows(self, rows: list[AnchorRow]) -> None:
        """替换所有锚点行。"""

        self.setRowCount(0)
        for row_data in rows:
            self.add_anchor(row_data)

    def row_model(self, row: int) -> AnchorRow | None:
        """读取指定行模型。"""

        if row < 0 or row >= self.rowCount():
            return None
        anchor_id = self._item_text(row, 0)
        action_roi = self._item_text(row, 1).split("  ")[0].strip()
        observe_roi = self._item_text(row, 4).split("  ")[0].strip()
        if not anchor_id or not action_roi:
            return None
        return AnchorRow(
            anchor_id=anchor_id,
            action_roi=action_roi,
            action=self._combo_data(row, 2) or "click",
            ocr_enabled=self._checkbox_value(row, 3),
            observe_roi=observe_roi,
            requires_confirmation=self._checkbox_value(row, 5),
        )

    def row_models(self) -> list[AnchorRow]:
        """返回全部行模型。"""

        rows: list[AnchorRow] = []
        for row in range(self.rowCount()):
            row_data = self.row_model(row)
            if row_data is not None:
                rows.append(row_data)
        return rows

    def remove_row(self, row: int) -> AnchorRow | None:
        """删除并返回行模型。"""

        row_data = self.row_model(row)
        if 0 <= row < self.rowCount():
            self.removeRow(row)
            self.rebind_row_widgets()
        return row_data

    def update_roi_label(self, roi_name: str, label: str) -> None:
        """更新引用指定 ROI 的坐标显示。"""

        for row in range(self.rowCount()):
            for column in (1, 4):
                text = self._item_text(row, column)
                name = text.split("  ")[0].strip()
                if name == roi_name:
                    self._set_item(row, column, label)

    def clear_observe_roi(self, row: int) -> str:
        """清空指定行观察 ROI。"""

        observe = self._item_text(row, 4).split("  ")[0].strip()
        self._set_item(row, 4, "")
        checkbox = self.cellWidget(row, 3)
        if isinstance(checkbox, QCheckBox):
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        return observe

    def set_observe_roi(self, row: int, roi_name: str) -> None:
        """设置指定行观察 ROI 名称。

        Args:
            row: 表格行号。
            roi_name: 观察 ROI 名称。
        """

        if 0 <= row < self.rowCount():
            self._set_item(row, 4, roi_name)

    def remove_rows_by_roi(self, roi_name: str) -> None:
        """根据动作 ROI 删除对应锚点行。"""

        for row in range(self.rowCount() - 1, -1, -1):
            row_data = self.row_model(row)
            if row_data and row_data.action_roi == roi_name:
                self.removeRow(row)
            elif row_data and row_data.observe_roi == roi_name:
                self.clear_observe_roi(row)
        self.rebind_row_widgets()

    def rebind_row_widgets(self) -> None:
        """重新绑定行号相关控件。"""

        for row in range(self.rowCount()):
            delete_btn = self.cellWidget(row, 6)
            if isinstance(delete_btn, QPushButton):
                try:
                    delete_btn.clicked.disconnect()
                except TypeError:
                    pass
                delete_btn.clicked.connect(
                    lambda _checked=False, r=row: self.row_delete_requested.emit(r)
                )
            ocr = self.cellWidget(row, 3)
            if isinstance(ocr, QCheckBox):
                try:
                    ocr.toggled.disconnect()
                except TypeError:
                    pass
                ocr.toggled.connect(
                    lambda checked, r=row: self.row_ocr_toggled.emit(r, checked)
                )

    def _action_combo(self, action: str) -> QComboBox:
        """创建动作下拉框。"""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        for key, label in ACTION_OPTIONS:
            combo.addItem(label, key)
        index = combo.findData(action)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(lambda _index: self._emit_widget_changed(combo))
        return combo

    def _checkbox(self, checked: bool, role: str) -> QCheckBox:
        """创建复选框。"""

        checkbox = QCheckBox()
        checkbox.setObjectName("TableCheck")
        set_embedded_editor_height(checkbox)
        checkbox.setChecked(checked)
        if role == "ocr":
            checkbox.toggled.connect(lambda value: self._emit_ocr_changed(checkbox, value))
        else:
            checkbox.toggled.connect(lambda _value: self._emit_widget_changed(checkbox))
        return checkbox

    def _emit_widget_changed(self, widget) -> None:
        """控件变更时发出行变更信号。"""

        row = self.indexAt(widget.pos()).row()
        if row >= 0:
            self.row_changed.emit(row)

    def _emit_ocr_changed(self, checkbox: QCheckBox, checked: bool) -> None:
        """OCR 复选框变更时发出信号。"""

        row = self.indexAt(checkbox.pos()).row()
        if row >= 0:
            self.row_ocr_toggled.emit(row, checked)
            self.row_changed.emit(row)

    def _set_item(self, row: int, column: int, text: str) -> None:
        """设置单元格文本。"""

        item = self.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, column, item)
        item.setText(text)
        if column in (1, 4):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _store_row(self, row: int, row_data: AnchorRow) -> None:
        """把行模型缓存到首列。"""

        item = self.item(row, 0)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, row_data)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """表格文本变更时发出行变更。"""

        self.row_changed.emit(item.row())

    def _item_text(self, row: int, column: int) -> str:
        """读取单元格文本。"""

        item = self.item(row, column)
        return item.text().strip() if item else ""

    def _combo_data(self, row: int, column: int) -> str:
        """读取下拉框数据。"""

        widget = self.cellWidget(row, column)
        return str(widget.currentData()) if isinstance(widget, QComboBox) else ""

    def _checkbox_value(self, row: int, column: int) -> bool:
        """读取复选框值。"""

        widget = self.cellWidget(row, column)
        return widget.isChecked() if isinstance(widget, QCheckBox) else False
