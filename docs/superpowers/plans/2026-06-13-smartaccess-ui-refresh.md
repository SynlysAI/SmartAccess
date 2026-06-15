# SmartAccess 界面刷新实施计划

> **给 agentic workers：** 必须使用子技能：推荐使用 `superpowers:subagent-driven-development`，或使用 `superpowers:executing-plans` 按任务执行。步骤使用 checkbox（`- [ ]`）语法跟踪。

**目标：** 将 SmartAccess PyQt 客户端重构为现代浅色卡片式工作台，同时保持现有业务逻辑不变。

**架构：** 第一阶段保留 PyQt6 标准控件，通过全局 QSS、少量 UI helper、稳定 `objectName` 和表格初始化属性完成视觉升级。布局仍使用现有 `QSplitter`、页面构建方法和 ViewModel 调用，只替换表现层容器、控件高度、边距和样式选择器。

**技术栈：** Python 3.11+、PyQt6、Qt QSS、现有 `smartaccess` 桌面模块。

---

## 文件结构

- 修改：`src/smartaccess/desktop/shell/theme.py`
  - 负责全局配色、按钮、表单、导航、卡片、表格和滚动条 QSS。
- 修改：`src/smartaccess/desktop/shell/main_window.py`
  - 负责主窗口浅灰背景、顶部栏、导航图标预留位和右侧上下文栏。
- 新建：`src/smartaccess/desktop/widgets/cards.py`
  - 负责创建统一卡片容器，避免页面里重复设置 `QFrame#Card`、padding 和 spacing。
- 新建：`src/smartaccess/desktop/widgets/table_style.py`
  - 负责统一 `QTableWidget` 行高、网格、表头、选择和内嵌控件高度。
- 修改：`src/smartaccess/desktop/pages/calibration_page.py`
  - 负责设备接入页面的表单、窗口列表、截图画布和锚点表格卡片化。
- 修改：`src/smartaccess/desktop/pages/workflow_page.py`
  - 负责工作流列表、元数据表单、AI 输入、步骤表和结果区卡片化。
- 修改：`src/smartaccess/desktop/widgets/anchor_table.py`
  - 负责锚点表行高、按钮、下拉框、复选框和表格边界。
- 修改：`src/smartaccess/desktop/widgets/workflow_step_table.py`
  - 负责步骤表行高、列内控件高度和行操作按钮。
- 修改：`src/smartaccess/desktop/widgets/condition_editor.py`
  - 负责 OCR 条件编辑器内控件最小高度和对象名。
- 修改：`src/smartaccess/desktop/widgets/roi_canvas.py`
  - 负责截图画布背景、边框和对象名。
- 修改：`src/smartaccess/desktop/widgets/timeline.py`
  - 负责运行监控时间线表格复用统一表格样式。
- 修改：`src/smartaccess/desktop/pages/template_page.py`
  - 负责模板页过滤区和表格卡片化，保证全局表格样式一致。
- 修改：`src/smartaccess/desktop/pages/dashboard_page.py`
  - 负责概览页统计和两张表卡片化，保证全局表格样式一致。

## 范围说明

- 第一阶段不新增 `qfluentwidgets` 依赖。
- 不改 `runtime`、`viewmodels`、合同模型和持久化服务。
- 不新增大量 UI 单测；验证使用 `compileall`、v2 桌面窗口离屏构建检查、现有测试子集和人工桌面验收。

---

### 任务 1：全局 QSS 主题

**文件：**
- 修改：`src/smartaccess/desktop/shell/theme.py`
- 验证：内联 Python 导入和 QSS 内容检查命令

- [ ] **步骤 1：替换为平衡型工作台配色**

将 `theme.py` 顶部常量更新为：

```python
CANVAS = "#F5F7FA"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#FAFBFC"
SURFACE_MUTED = "#F0F3F8"
BORDER = "#E2E8F0"
BORDER_LIGHT = "#EBEBEF"
BORDER_STRONG = "#CBD5E1"
TEXT = "#111827"
TEXT_MUTED = "#4B5B73"
TEXT_SUBTLE = "#7A8798"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_PRESSED = "#1E40AF"
PRIMARY_SOFT = "#E8F1FF"
SUCCESS = "#0F9F6E"
WARNING = "#C77900"
DANGER = "#DC2626"
DANGER_SOFT = "#FFF1F2"
SHADOW = "rgba(15, 23, 42, 0.06)"
```

- [ ] **步骤 2：替换 `build_qss()` 的全局样式表**

将 `build_qss()` 中现有的 `return f"""..."""` 替换为：

```python
    return f"""
QWidget {{
    background-color: {CANVAS};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}
QMainWindow, QMainWindow > QWidget {{
    background-color: {CANVAS};
}}
QFrame#TopBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QFrame#Card, QFrame#RightPanel {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#SectionCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#AppTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
QLabel#PageHint, QLabel#SectionTitle {{
    color: {TEXT_MUTED};
    background: transparent;
}}
QListWidget#NavList {{
    background: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
    padding: 12px 10px;
    outline: 0;
}}
QListWidget#NavList::item {{
    min-height: 42px;
    padding: 10px 12px 10px 36px;
    margin: 4px 0px;
    border-radius: 8px;
    color: {TEXT_MUTED};
    border-left: 3px solid transparent;
}}
QListWidget#NavList::item:hover {{
    background: {SURFACE_ALT};
    color: {TEXT};
}}
QListWidget#NavList::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_HOVER};
    border-left: 3px solid {PRIMARY};
    font-weight: 700;
}}
QPushButton {{
    background: {PRIMARY};
    color: #ffffff;
    border: 1px solid {PRIMARY};
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 22px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {PRIMARY_HOVER};
    border-color: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background: {PRIMARY_PRESSED};
    border-color: {PRIMARY_PRESSED};
}}
QPushButton:disabled {{
    background: {SURFACE_MUTED};
    color: {TEXT_SUBTLE};
    border-color: {BORDER};
}}
QPushButton#Secondary {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
}}
QPushButton#Secondary:hover {{
    background: {SURFACE_ALT};
    border-color: {PRIMARY};
    color: {PRIMARY_HOVER};
}}
QPushButton#Danger {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #FDA4AF;
}}
QPushButton#Danger:hover {{
    background: #FFE4E6;
    border-color: {DANGER};
}}
QPushButton#TableAction {{
    background: {SURFACE};
    color: {PRIMARY_HOVER};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 0px 6px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#TableAction:hover {{
    border-color: {PRIMARY};
    background: {PRIMARY_SOFT};
}}
QPushButton#TableDanger {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #FDA4AF;
    border-radius: 5px;
    padding: 0px 6px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {PRIMARY};
}}
QComboBox::drop-down {{
    width: 24px;
    border: none;
}}
QCheckBox {{
    background: transparent;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QListWidget {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: 0;
}}
QListWidget::item {{
    min-height: 30px;
    padding: 6px 10px;
    border-radius: 5px;
}}
QListWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_HOVER};
}}
QTableWidget {{
    background: {SURFACE};
    alternate-background-color: #FBFCFE;
    color: {TEXT};
    border: none;
    border-radius: 0px;
    gridline-color: {BORDER_LIGHT};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {BORDER_LIGHT};
}}
QTableWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 9px 10px;
    font-weight: 700;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 8px;
}}
QStatusBar {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}
QGraphicsView#RoiCanvas {{
    background: {SURFACE_MUTED};
    border: none;
    border-radius: 8px;
}}
"""
```

- [ ] **步骤 3：验证主题导入和关键选择器**

运行：

```powershell
python -c "from smartaccess.desktop.shell.theme import build_qss; qss=build_qss(); assert 'QFrame#Card' in qss; assert 'QTableWidget::item' in qss; assert '#F5F7FA' in qss; print('theme qss ok')"
```

期望输出：

```text
theme qss ok
```

- [ ] **步骤 4：提交任务 1**

运行：

```powershell
git add src/smartaccess/desktop/shell/theme.py
git commit -m "优化 v2 桌面全局主题" -m "- 更新浅色工作台配色" -m "- 添加卡片、导航、表格和表单 QSS" -m "- 统一主次按钮和危险按钮样式"
```

期望输出包含：

```text
优化 v2 桌面全局主题
```

---

### 任务 2：共享 UI 工具

**文件：**
- 新建：`src/smartaccess/desktop/widgets/cards.py`
- 新建：`src/smartaccess/desktop/widgets/table_style.py`
- 验证：内联导入命令

- [ ] **步骤 1：创建卡片 helper**

创建 `src/smartaccess/desktop/widgets/cards.py`：

```python
"""桌面端卡片容器工具。"""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QVBoxLayout


def create_card(
    *,
    object_name: str = "Card",
    margins: tuple[int, int, int, int] = (16, 16, 16, 16),
    spacing: int = 10,
) -> tuple[QFrame, QVBoxLayout]:
    """创建统一卡片容器。

    Args:
        object_name: QSS 使用的对象名。
        margins: 卡片内部边距，顺序为左、上、右、下。
        spacing: 卡片内部布局间距。

    Returns:
        卡片框架和其垂直布局。
    """

    card = QFrame()
    card.setObjectName(object_name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return card, layout
```

- [ ] **步骤 2：创建表格样式 helper**

创建 `src/smartaccess/desktop/widgets/table_style.py`：

```python
"""桌面端表格样式工具。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QWidget


def configure_data_table(
    table: QTableWidget,
    *,
    row_height: int = 42,
    stretch_last: bool = False,
) -> None:
    """应用统一数据表格表现层设置。

    Args:
        table: 需要设置的数据表格。
        row_height: 默认行高。
        stretch_last: 是否拉伸最后一列。
    """

    table.setObjectName("DataTable")
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.verticalHeader().setMinimumSectionSize(row_height)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignVCenter)
    table.horizontalHeader().setStretchLastSection(stretch_last)


def set_embedded_editor_height(widget: QWidget, *, height: int = 32) -> None:
    """设置表格内嵌编辑控件高度。

    Args:
        widget: 表格内嵌控件。
        height: 控件最小高度。
    """

    widget.setMinimumHeight(height)


def interactive_header(table: QTableWidget) -> QHeaderView:
    """返回表格水平表头并设置交互式列宽。

    Args:
        table: 目标表格。

    Returns:
        已设置为交互式列宽的水平表头。
    """

    header = table.horizontalHeader()
    for column in range(table.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
    return header
```

- [ ] **步骤 3：验证 helper 导入**

运行：

```powershell
python -c "from smartaccess.desktop.widgets.cards import create_card; from smartaccess.desktop.widgets.table_style import configure_data_table; print(create_card.__name__, configure_data_table.__name__)"
```

期望输出：

```text
create_card configure_data_table
```

- [ ] **步骤 4：提交任务 2**

运行：

```powershell
git add src/smartaccess/desktop/widgets/cards.py src/smartaccess/desktop/widgets/table_style.py
git commit -m "新增 v2 桌面 UI 样式工具" -m "- 添加统一卡片容器 helper" -m "- 添加统一数据表格配置 helper"
```

期望输出包含：

```text
新增 v2 桌面 UI 样式工具
```

---

### 任务 3：主窗口导航和外壳

**文件：**
- 修改：`src/smartaccess/desktop/shell/main_window.py`
- 验证：离屏构建主窗口

- [ ] **步骤 1：补充导航图标所需导入**

更新 `main_window.py` 导入：

```python
from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)
```

- [ ] **步骤 2：移除右侧面板内联样式**

删除 `_build_right_panel()` 中的 `panel.setStyleSheet(...)` 代码块。保留 `panel.setObjectName("RightPanel")`，由全局 QSS 控制。

`_build_right_panel()` 开头应为：

```python
        panel = QFrame()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
```

- [ ] **步骤 3：给导航添加图标和间距**

替换 `_build_nav()`：

```python
    def _build_nav(self) -> QListWidget:
        """构建左侧导航。

        Returns:
            导航列表部件。
        """

        self._nav.setFixedWidth(248)
        self._nav.setIconSize(QSize(18, 18))
        icons = [
            QStyle.StandardPixmap.SP_ComputerIcon,
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            QStyle.StandardPixmap.SP_MediaPlay,
            QStyle.StandardPixmap.SP_DirIcon,
            QStyle.StandardPixmap.SP_FileDialogInfoView,
        ]
        for index, (title, hint) in enumerate(_NAV_ITEMS):
            item = QListWidgetItem(title)
            item.setIcon(self.style().standardIcon(icons[index]))
            item.setToolTip(hint)
            self._nav.addItem(item)
        return self._nav
```

- [ ] **步骤 4：验证主窗口离屏构建**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.bootstrap.runtime import build_runtime_facade; from smartaccess.desktop.shell.main_window import MainWindow; from smartaccess.desktop.shell.theme import apply_theme; from smartaccess.shared.config.settings import AppSettings; app=QApplication([]); apply_theme(app); settings=AppSettings(workspace_dir='tmp-ui-smoke'); facade=build_runtime_facade(settings); window=MainWindow(settings, facade=facade); assert window._nav.count()==5; assert window._stack.count()==5; assert window._nav.iconSize().width()==18; print('v2 shell ok')"
```

期望输出：

```text
v2 shell ok
```

- [ ] **步骤 5：删除临时 smoke 工作区**

运行：

```powershell
if (Test-Path "tmp-ui-smoke") { Remove-Item -LiteralPath "tmp-ui-smoke" -Recurse -Force }
```

期望结果：命令无输出并正常退出。

- [ ] **步骤 6：提交任务 3**

运行：

```powershell
git add src/smartaccess/desktop/shell/main_window.py
git commit -m "优化 v2 主窗口导航样式" -m "- 为导航项添加图标预留位" -m "- 使用全局 QSS 管理右侧上下文栏" -m "- 调整导航栏宽度和间距"
```

期望输出包含：

```text
优化 v2 主窗口导航样式
```

---

### 任务 4：表格组件和内嵌编辑器

**文件：**
- 修改：`src/smartaccess/desktop/widgets/anchor_table.py`
- 修改：`src/smartaccess/desktop/widgets/workflow_step_table.py`
- 修改：`src/smartaccess/desktop/widgets/condition_editor.py`
- 修改：`src/smartaccess/desktop/widgets/timeline.py`
- 验证：内联控件构建命令

- [ ] **步骤 1：给 `AnchorTable` 应用表格 helper**

添加导入：

```python
from smartaccess.desktop.widgets.table_style import (
    configure_data_table,
    interactive_header,
    set_embedded_editor_height,
)
```

在 `AnchorTable.__init__()` 中，将手动的 vertical header 和 header 设置代码替换为：

```python
        configure_data_table(self, row_height=44)
        header = interactive_header(self)
        header.setStretchLastSection(False)
```

保留现有列宽设置。

- [ ] **步骤 2：提高 `AnchorTable` 内嵌控件高度**

更新 `_action_combo()`：

```python
        combo = QComboBox()
        set_embedded_editor_height(combo)
```

更新 `_checkbox()`：

```python
        checkbox = QCheckBox()
        checkbox.setObjectName("TableCheck")
        set_embedded_editor_height(checkbox)
```

更新 `add_anchor()` 中删除按钮尺寸：

```python
        delete_btn.setFixedSize(58, 30)
```

- [ ] **步骤 3：给 `WorkflowStepTable` 应用表格 helper**

添加导入：

```python
from smartaccess.desktop.widgets.table_style import (
    configure_data_table,
    interactive_header,
    set_embedded_editor_height,
)
```

在 `WorkflowStepTable.__init__()` 中，将 vertical header 和 header 设置替换为：

```python
        configure_data_table(self, row_height=46)
        interactive_header(self)
```

保留现有列宽设置。

- [ ] **步骤 4：设置工作流步骤表内控件高度**

在 `_action_combo()` 和 `_anchor_combo()` 中，创建 `combo` 后添加：

```python
        set_embedded_editor_height(combo)
```

在 `add_step()` 中分别添加：

```python
        value = QLineEdit("" if step.value is None else str(step.value))
        set_embedded_editor_height(value)
```

```python
        wait = QDoubleSpinBox()
        set_embedded_editor_height(wait)
```

```python
        confirm = QComboBox()
        set_embedded_editor_height(confirm)
```

在 `insert_wait()` 中分别添加：

```python
        value = QLineEdit("")
        set_embedded_editor_height(value)
```

```python
        wait = QDoubleSpinBox()
        set_embedded_editor_height(wait)
```

```python
        confirm = QComboBox()
        set_embedded_editor_height(confirm)
```

- [ ] **步骤 5：调整工作流行操作按钮尺寸**

在 `_row_buttons()` 中将：

```python
            button.setFixedSize(52, 26)
```

改为：

```python
            button.setFixedSize(54, 30)
```

- [ ] **步骤 6：设置 `ConditionEditor` 控件样式对象名和高度**

在 `condition_editor.py` 中添加导入：

```python
from smartaccess.desktop.widgets.table_style import set_embedded_editor_height
```

创建每个控件后设置对象名和高度：

```python
        self.match_mode = QComboBox()
        self.match_mode.setObjectName("ConditionMode")
        set_embedded_editor_height(self.match_mode)
```

```python
        self.expected_text = QLineEdit()
        self.expected_text.setObjectName("ConditionText")
        self.expected_text.setPlaceholderText("期望文本")
        set_embedded_editor_height(self.expected_text)
```

```python
        self.timeout_seconds = QDoubleSpinBox()
        self.timeout_seconds.setObjectName("ConditionTimeout")
        set_embedded_editor_height(self.timeout_seconds)
```

- [ ] **步骤 7：给 `TimelineTable` 应用表格 helper**

添加导入：

```python
from smartaccess.desktop.widgets.table_style import configure_data_table
```

在 `TimelineTable.__init__()` 设置表头后添加：

```python
        configure_data_table(self, row_height=42, stretch_last=True)
```

保留现有 `horizontalHeader().setSectionResizeMode(...)` 调用。

- [ ] **步骤 8：验证表格控件构建**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.desktop.widgets.anchor_table import AnchorTable, AnchorRow; from smartaccess.desktop.widgets.workflow_step_table import WorkflowStepTable, StepRow; app=QApplication([]); anchors=AnchorTable(); anchors.add_anchor(AnchorRow(anchor_id='a1', action_roi='a1')); steps=WorkflowStepTable(); steps.add_step(StepRow(step_id='s1', action='click', anchor_id='a1'), ['a1']); assert anchors.verticalHeader().defaultSectionSize()>=40; assert steps.verticalHeader().defaultSectionSize()>=40; print('v2 tables ok')"
```

期望输出：

```text
v2 tables ok
```

- [ ] **步骤 9：提交任务 4**

运行：

```powershell
git add src/smartaccess/desktop/widgets/anchor_table.py src/smartaccess/desktop/widgets/workflow_step_table.py src/smartaccess/desktop/widgets/condition_editor.py src/smartaccess/desktop/widgets/timeline.py
git commit -m "优化 v2 数据表格表现" -m "- 统一表格行高和无垂直网格样式" -m "- 调整表格内嵌编辑控件高度" -m "- 优化行操作按钮尺寸"
```

期望输出包含：

```text
优化 v2 数据表格表现
```

---

### 任务 5：设备接入页面卡片化

**文件：**
- 修改：`src/smartaccess/desktop/pages/calibration_page.py`
- 修改：`src/smartaccess/desktop/widgets/roi_canvas.py`
- 验证：离屏构建设备接入页面

- [ ] **步骤 1：导入卡片 helper**

在 `calibration_page.py` 中添加：

```python
from smartaccess.desktop.widgets.cards import create_card
```

- [ ] **步骤 2：将左侧面板改为卡片**

将 `_build_left_panel()` 开头：

```python
        panel = QWidget()
        panel.setMinimumWidth(290)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(10)
```

替换为：

```python
        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(300)
```

保留所有子控件和信号连接。

- [ ] **步骤 3：将中间画布面板改为卡片**

将 `_build_center_panel()` 开头：

```python
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)
```

替换为：

```python
        panel, layout = create_card(margins=(10, 10, 10, 10), spacing=8)
```

保留 `self._canvas = RoiCanvas()` 和 `layout.addWidget(self._canvas, 1)`。

- [ ] **步骤 4：将右侧锚点表格面板改为卡片**

将 `_build_right_panel()` 开头：

```python
        panel = QWidget()
        panel.setMinimumWidth(500)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
```

替换为：

```python
        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(520)
```

保留添加按钮行和表格创建逻辑。

- [ ] **步骤 5：保持截图为主按钮**

在 `_build_left_panel()` 中，`scan_btn` 保持次按钮：

```python
        scan_btn.setObjectName("Secondary")
```

不要给 `self._capture_btn` 设置 `Secondary`，让它使用默认 Primary 样式。

- [ ] **步骤 6：设置 `RoiCanvas` 对象名和背景**

在 `RoiCanvas.__init__()` 中，`super().__init__(self._scene, parent)` 后添加：

```python
        self.setObjectName("RoiCanvas")
```

将背景刷改为：

```python
        self.setBackgroundBrush(QBrush(QColor("#F0F3F8")))
```

- [ ] **步骤 7：验证设备接入页面构建**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.bootstrap.runtime import build_runtime_facade; from smartaccess.desktop.pages.calibration_page import CalibrationPage; from smartaccess.desktop.shell.theme import apply_theme; from smartaccess.shared.config.settings import AppSettings; app=QApplication([]); apply_theme(app); settings=AppSettings(workspace_dir='tmp-ui-smoke'); page=CalibrationPage(build_runtime_facade(settings)); assert page._table.verticalHeader().defaultSectionSize()>=40; assert page._canvas.objectName()=='RoiCanvas'; print('v2 calibration ok')"
```

期望输出：

```text
v2 calibration ok
```

- [ ] **步骤 8：删除临时 smoke 工作区**

运行：

```powershell
if (Test-Path "tmp-ui-smoke") { Remove-Item -LiteralPath "tmp-ui-smoke" -Recurse -Force }
```

期望结果：命令无输出并正常退出。

- [ ] **步骤 9：提交任务 5**

运行：

```powershell
git add src/smartaccess/desktop/pages/calibration_page.py src/smartaccess/desktop/widgets/roi_canvas.py
git commit -m "卡片化 v2 设备接入页面" -m "- 将表单、画布和锚点表格放入卡片容器" -m "- 调整截图画布对象名和背景色" -m "- 保持扫描与截图交互逻辑不变"
```

期望输出包含：

```text
卡片化 v2 设备接入页面
```

---

### 任务 6：工作流页面卡片化

**文件：**
- 修改：`src/smartaccess/desktop/pages/workflow_page.py`
- 验证：离屏构建工作流页面

- [ ] **步骤 1：导入卡片 helper**

添加：

```python
from smartaccess.desktop.widgets.cards import create_card
```

- [ ] **步骤 2：将工作流列表面板改为卡片**

将 `_build_left_panel()` 开头：

```python
        panel = QWidget()
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)
```

替换为：

```python
        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        panel.setMinimumWidth(310)
```

保留列表设置和右键菜单逻辑。

- [ ] **步骤 3：将编辑区改为卡片**

将 `_build_editor()` 开头：

```python
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
```

替换为：

```python
        panel, layout = create_card(margins=(14, 14, 14, 14), spacing=12)
```

- [ ] **步骤 4：给大型工作流编辑控件设置对象名**

创建 `_ai_prompt` 后添加：

```python
        self._ai_prompt.setObjectName("PromptEditor")
```

创建 `_result` 后添加：

```python
        self._result.setObjectName("ResultEditor")
```

- [ ] **步骤 5：保持按钮主次层级**

确保这些按钮仍为 `Secondary`：`new_btn`、`add_action_btn`、`insert_action_btn`、`wait_btn`、`check_btn`、`ai_btn`。

确保 `save_btn` 不设置对象名，让它使用 Primary 样式：

```python
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
```

- [ ] **步骤 6：验证工作流页面构建**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.bootstrap.runtime import build_runtime_facade; from smartaccess.desktop.pages.workflow_page import WorkflowPage; from smartaccess.desktop.shell.theme import apply_theme; from smartaccess.shared.config.settings import AppSettings; app=QApplication([]); apply_theme(app); settings=AppSettings(workspace_dir='tmp-ui-smoke'); page=WorkflowPage(build_runtime_facade(settings)); assert page._steps.verticalHeader().defaultSectionSize()>=40; assert page._ai_prompt.objectName()=='PromptEditor'; print('v2 workflow ok')"
```

期望输出：

```text
v2 workflow ok
```

- [ ] **步骤 7：删除临时 smoke 工作区**

运行：

```powershell
if (Test-Path "tmp-ui-smoke") { Remove-Item -LiteralPath "tmp-ui-smoke" -Recurse -Force }
```

期望结果：命令无输出并正常退出。

- [ ] **步骤 8：提交任务 6**

运行：

```powershell
git add src/smartaccess/desktop/pages/workflow_page.py
git commit -m "卡片化 v2 工作流设计页面" -m "- 将工作流列表和编辑区放入卡片容器" -m "- 标记 AI 输入和结果输出编辑器" -m "- 保持工作流操作按钮主次层级"
```

期望输出包含：

```text
卡片化 v2 工作流设计页面
```

---

### 任务 7：次级页面一致性

**文件：**
- 修改：`src/smartaccess/desktop/pages/template_page.py`
- 修改：`src/smartaccess/desktop/pages/dashboard_page.py`
- 验证：离屏构建次级页面

- [ ] **步骤 1：在 `template_page.py` 导入 helper**

添加：

```python
from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.table_style import configure_data_table
```

- [ ] **步骤 2：将模板过滤区和表格放入卡片**

在 `TemplatePage.__init__()` 中，将：

```python
        root.addLayout(self._build_filters())

        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, 1)
```

替换为：

```python
        filter_card, filter_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        filter_layout.addLayout(self._build_filters())
        root.addWidget(filter_card)

        table_card, table_layout = create_card(margins=(0, 0, 0, 0), spacing=0)
        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        configure_data_table(self._table, row_height=42, stretch_last=True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)
        root.addWidget(table_card, 1)
```

- [ ] **步骤 3：在 `dashboard_page.py` 导入 helper**

添加：

```python
from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.table_style import configure_data_table
```

- [ ] **步骤 4：将概览统计和表格放入卡片**

在 `DashboardPage.__init__()` 中，`root.addWidget(title)` 后用以下结构替换旧的统计和表格设置：

```python
        stats_card, stats_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        self._stats = QGridLayout()
        stats_layout.addLayout(self._stats)
        root.addWidget(stats_card)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("Secondary")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn)

        runs_card, runs_layout = create_card(margins=(0, 0, 0, 0), spacing=0)
        self._runs = QTableWidget(0, 3)
        self._runs.setHorizontalHeaderLabels(("会话", "工作流", "状态"))
        configure_data_table(self._runs, row_height=42, stretch_last=True)
        runs_layout.addWidget(self._runs)
        root.addWidget(runs_card, 1)

        incidents_card, incidents_layout = create_card(margins=(0, 0, 0, 0), spacing=0)
        self._incidents = QTableWidget(0, 4)
        self._incidents.setHorizontalHeaderLabels(("异常", "会话", "类型", "详情"))
        configure_data_table(self._incidents, row_height=42, stretch_last=True)
        incidents_layout.addWidget(self._incidents)
        root.addWidget(incidents_card, 1)
```

删除旧的直接 `self._stats`、`self._runs` 和 `self._incidents` 设置，避免重复添加。

- [ ] **步骤 5：验证次级页面构建**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.bootstrap.runtime import build_runtime_facade; from smartaccess.desktop.pages.dashboard_page import DashboardPage; from smartaccess.desktop.pages.template_page import TemplatePage; from smartaccess.desktop.shell.theme import apply_theme; from smartaccess.shared.config.settings import AppSettings; app=QApplication([]); apply_theme(app); settings=AppSettings(workspace_dir='tmp-ui-smoke'); facade=build_runtime_facade(settings); template=TemplatePage(facade); dashboard=DashboardPage(facade); assert template._table.verticalHeader().defaultSectionSize()>=40; assert dashboard._runs.verticalHeader().defaultSectionSize()>=40; print('v2 secondary pages ok')"
```

期望输出：

```text
v2 secondary pages ok
```

- [ ] **步骤 6：删除临时 smoke 工作区**

运行：

```powershell
if (Test-Path "tmp-ui-smoke") { Remove-Item -LiteralPath "tmp-ui-smoke" -Recurse -Force }
```

期望结果：命令无输出并正常退出。

- [ ] **步骤 7：提交任务 7**

运行：

```powershell
git add src/smartaccess/desktop/pages/template_page.py src/smartaccess/desktop/pages/dashboard_page.py
git commit -m "统一 v2 次级页面卡片样式" -m "- 卡片化模板过滤区和模板表格" -m "- 卡片化概览统计区和数据表格" -m "- 复用统一数据表格配置"
```

期望输出包含：

```text
统一 v2 次级页面卡片样式
```

---

### 任务 8：端到端验证和视觉检查

**文件：**
- 默认不改源码；只有前序任务引入已验证缺陷时才修复。
- 验证：编译、离屏构建、选定 pytest 命令、可见桌面启动。

- [ ] **步骤 1：编译 v2 桌面包**

运行：

```powershell
python -m compileall src/smartaccess/desktop
```

期望结果：命令结束时没有 `SyntaxError` 或 `IndentationError`。

- [ ] **步骤 2：运行 v2 主窗口离屏 smoke**

运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -c "from PyQt6.QtWidgets import QApplication; from smartaccess.bootstrap.runtime import build_runtime_facade; from smartaccess.desktop.shell.main_window import MainWindow; from smartaccess.desktop.shell.theme import apply_theme; from smartaccess.shared.config.settings import AppSettings; app=QApplication([]); apply_theme(app); settings=AppSettings(workspace_dir='tmp-ui-smoke'); facade=build_runtime_facade(settings); window=MainWindow(settings, facade=facade); assert window._nav.count()==5; assert window._stack.count()==5; window._nav.setCurrentRow(1); assert window._stack.currentIndex()==1; print('v2 desktop smoke ok')"
```

期望输出：

```text
v2 desktop smoke ok
```

- [ ] **步骤 3：删除临时 smoke 工作区**

运行：

```powershell
if (Test-Path "tmp-ui-smoke") { Remove-Item -LiteralPath "tmp-ui-smoke" -Recurse -Force }
```

期望结果：命令无输出并正常退出。

- [ ] **步骤 4：运行现有非视觉回归子集**

运行：

```powershell
pytest tests/integration/test_facade.py tests/integration/test_services.py -q
```

期望输出包含：

```text
passed
```

如果当前环境缺少与 UI 改造无关的可选依赖，记录缺失依赖和失败命令，再继续步骤 5。

- [ ] **步骤 5：启动可见 v2 桌面进行视觉验收**

运行：

```powershell
python run_desktop.py
```

人工检查：

- 主窗口背景是 `#F5F7FA` 浅灰色。
- 左侧导航每项有图标位，选中项左侧有蓝色竖线。
- 设备接入页面的表单、窗口列表、截图画布、锚点表格位于独立白色卡片。
- 工作流设计页面的工作流列表、元数据表单、AI 输入、步骤表、结果区分区清晰。
- 锚点表和步骤表行高不低于 40px，内嵌输入框和下拉框不贴边。
- 表格看不到垂直网格线，水平分隔线很浅。
- 保存、截图、添加锚点是蓝色主按钮；扫描、新建、检查、AI 生成是白底灰边次按钮；删除是红色危险态。

- [ ] **步骤 6：提交验证中发现的修复**

如果步骤 1-5 需要源码修复，只提交已验证的修复：

```powershell
git add src/smartaccess/desktop
git commit -m "修正 v2 UI 验收问题" -m "- 修复桌面启动和视觉验收中发现的表现层问题"
```

如果没有需要修复的源码，不创建提交。

- [ ] **步骤 7：记录最终 git 状态**

运行：

```powershell
git status --short
```

期望结果：只剩实现前已有的无关变更，例如 `.gitignore` 和 `v2重构点.txt`。

---

## 自检

- Spec 覆盖：任务 1-7 覆盖全局 QSS、卡片布局、导航图标位、表格行高和网格处理、主次/危险按钮、输入 padding，以及 `qfluentwidgets` 第一阶段暂缓。
- 占位扫描：计划包含具体文件、命令、代码片段和期望输出，没有需要临场补全的占位内容。
- 类型一致性：helper 名称为 `create_card`、`configure_data_table`、`set_embedded_editor_height`、`interactive_header`，后续任务均使用这些名称。
