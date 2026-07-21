"""锚点表格组件。"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from smartaccess.desktop.widgets.table_style import (
    NoWheelComboBox,
    configure_data_table,
    interactive_header,
    set_embedded_editor_height,
)

PRECHECK_OPTIONS = [
    ("none", "无"),
    ("image", "图像一致"),
    ("text", "文字一致"),
    ("image_text", "图像 + 文字"),
]


@dataclass(slots=True)
class AnchorRow:
    """锚点表格行模型。"""

    anchor_id: str
    target_roi: str
    precheck_mode: str = "none"
    validation_roi: str = ""


class AnchorTable(QTableWidget):
    """用于编辑锚点目标区域和执行前校验区域的表格。"""

    row_delete_requested = pyqtSignal(int)
    row_precheck_changed = pyqtSignal(int, str)
    row_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        """初始化锚点表格。"""

        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(
            ["锚点 ID", "目标区域", "执行前校验", "校验区域", "操作"]
        )
        configure_data_table(self, row_height=38)
        header = interactive_header(self)
        header.setStretchLastSection(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setColumnWidth(0, 190)
        self.setColumnWidth(1, 140)
        self.setColumnWidth(2, 130)
        self.setColumnWidth(3, 140)
        self.setColumnWidth(4, 50)
        self.itemChanged.connect(self._on_item_changed)

    def minimumSizeHint(self):
        """返回表格可接受的最小宽度，避免撑大父级窗口。"""

        return QSize(300, 120)

    def sizeHint(self):
        """返回合理默认尺寸，控制表格对布局空间的诉求。"""

        return QSize(560, 220)

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
        self._set_item(row, 1, row_data.target_roi)
        self.setCellWidget(row, 2, self._precheck_combo(row_data.precheck_mode))
        self._set_item(row, 3, row_data.validation_roi)
        delete_btn = QPushButton("×")
        delete_btn.setObjectName("TableDanger")
        delete_btn.setToolTip("删除锚点")
        delete_btn.setFixedSize(22, 22)
        delete_btn.clicked.connect(
            lambda _checked=False, current_row=row: self.row_delete_requested.emit(
                current_row
            )
        )
        self.setCellWidget(row, 4, delete_btn)
        self._store_row(row, row_data)
        self._stash_roi_name(row, 1, row_data.target_roi)
        self._stash_roi_name(row, 3, row_data.validation_roi)
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
        target_roi = self._roi_name(row, 1)
        validation_roi = self._roi_name(row, 3)
        if not anchor_id or not target_roi:
            return None
        return AnchorRow(
            anchor_id=anchor_id,
            target_roi=target_roi,
            precheck_mode=self._combo_data(row, 2) or "none",
            validation_roi=validation_roi,
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
            for column in (1, 3):
                item = self.item(row, column)
                text = self._item_text(row, column)
                stored = item.data(Qt.ItemDataRole.UserRole) if item else ""
                name = str(stored) if stored else text.split("  ")[0].strip()
                if name == roi_name:
                    self._set_item(row, column, label)
                    item = self.item(row, column)
                    if item is not None:
                        item.setData(Qt.ItemDataRole.UserRole, roi_name)

    def clear_validation_roi(self, row: int) -> str:
        """清空指定行的校验 ROI。"""

        validation_roi = self._roi_name(row, 3)
        self._set_item(row, 3, "")
        item = self.item(row, 3)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, "")
        return validation_roi

    def set_validation_roi(self, row: int, roi_name: str) -> None:
        """设置指定行的校验 ROI。

        Args:
            row: 表格行号。
            roi_name: 校验 ROI 名称。
        """

        if 0 <= row < self.rowCount():
            self._set_item(row, 3, roi_name)
            self._stash_roi_name(row, 3, roi_name)

    def remove_rows_by_roi(self, roi_name: str) -> None:
        """根据 ROI 名称删除或清理相关锚点行。"""

        for row in range(self.rowCount() - 1, -1, -1):
            row_data = self.row_model(row)
            if row_data and row_data.target_roi == roi_name:
                self.removeRow(row)
            elif row_data and row_data.validation_roi == roi_name:
                self.clear_validation_roi(row)
                combo = self.cellWidget(row, 2)
                if isinstance(combo, QComboBox):
                    combo.setCurrentIndex(0)
        self.rebind_row_widgets()

    def rebind_row_widgets(self) -> None:
        """重新绑定行号相关控件。"""

        for row in range(self.rowCount()):
            delete_btn = self.cellWidget(row, 4)
            if isinstance(delete_btn, QPushButton):
                try:
                    delete_btn.clicked.disconnect()
                except TypeError:
                    pass
                delete_btn.clicked.connect(
                    lambda _checked=False, current_row=row: self.row_delete_requested.emit(
                        current_row
                    )
                )
            combo = self.cellWidget(row, 2)
            if isinstance(combo, QComboBox):
                try:
                    combo.currentIndexChanged.disconnect()
                except TypeError:
                    pass
                combo.currentIndexChanged.connect(
                    lambda _index, current_combo=combo: self._emit_precheck_changed(
                        current_combo
                    )
                )

    def _precheck_combo(self, mode: str) -> QComboBox:
        """创建执行前校验方式下拉框。"""

        combo = NoWheelComboBox()
        combo.setObjectName("TableComboBox")
        set_embedded_editor_height(combo)
        for key, label in PRECHECK_OPTIONS:
            combo.addItem(label, key)
        index = combo.findData(mode)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(
            lambda _index, current_combo=combo: self._emit_precheck_changed(
                current_combo
            )
        )
        return combo

    def _emit_precheck_changed(self, combo: QComboBox) -> None:
        """执行前校验方式变化时发出信号。"""

        row = self.indexAt(combo.pos()).row()
        if row >= 0:
            self.row_precheck_changed.emit(row, str(combo.currentData() or "none"))
            self.row_changed.emit(row)

    def _set_item(self, row: int, column: int, text: str) -> None:
        """设置单元格文本。"""

        item = self.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, column, item)
        item.setText(text)
        if column in (1, 3):
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

    def _stash_roi_name(self, row: int, column: int, name: str) -> None:
        """将 ROI 名称存入单元格 UserRole。"""

        if not name:
            return
        item = self.item(row, column)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, name)

    def _roi_name(self, row: int, column: int) -> str:
        """从 UserRole 或文本解析 ROI 名称。"""

        item = self.item(row, column)
        if item is not None:
            stored = item.data(Qt.ItemDataRole.UserRole)
            if stored:
                return str(stored)
            return item.text().strip().split("  ")[0].strip()
        return ""

    def _combo_data(self, row: int, column: int) -> str:
        """读取下拉框数据。"""

        widget = self.cellWidget(row, column)
        return str(widget.currentData()) if isinstance(widget, QComboBox) else ""
