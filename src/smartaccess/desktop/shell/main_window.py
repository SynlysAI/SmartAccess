"""SmartAccess 主窗口。"""

from __future__ import annotations

import json
from pathlib import Path

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

from smartaccess.desktop.pages.calibration_page import CalibrationPage
from smartaccess.desktop.pages.dashboard_page import DashboardPage
from smartaccess.desktop.pages.monitoring_page import MonitoringPage
from smartaccess.desktop.pages.template_page import TemplatePage
from smartaccess.desktop.pages.workflow_page import WorkflowPage
from smartaccess.shared.config.settings import AppSettings
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.logging import get_logger

_NAV_ITEMS = [
    ("设备接入与校准", "窗口扫描、截图、ROI 和锚点配置"),
    ("工作流设计", "生成、编辑、检查和保存工作流"),
    ("运行监控", "执行工作流并查看日志和审计"),
    ("模板/平台", "模板发布、回滚和平台同步"),
    ("运行概览", "设备、模板、运行和异常概览"),
]


class MainWindow(QMainWindow):
    """SmartAccess 桌面主窗口。"""

    def __init__(
        self,
        settings: AppSettings,
        facade: RuntimeFacade | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """初始化主窗口。

        Args:
            settings: 应用配置。
            facade: 可选运行时门面。
            parent: 可选父级窗口。
        """

        super().__init__(parent)
        self._settings = settings
        self._facade = facade
        self._logger = get_logger()
        self._state_path = (
            Path(settings.workspace_dir) / "app_state" / "window_state.json"
        )

        self.setWindowTitle("SmartAccess")
        self.setMinimumSize(800, 500)
        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        self._stack = QStackedWidget()
        self._right_panel = self._build_right_panel()

        self._build_ui()
        self._restore_window_state()
        self._nav.setCurrentRow(0)
        self._logger.info("主窗口初始化完成")

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭窗口前保存 UI 状态。"""

        self._save_window_state()
        super().closeEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        """窗口状态变化时保存稳定的布局状态。"""

        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and not self.isMinimized():
            self._save_window_state()

    def _build_ui(self) -> None:
        """构建主窗口布局。"""

        center = QWidget()
        root = QVBoxLayout(center)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_nav(), 0)
        body.addWidget(self._stack, 1)
        body.addWidget(self._right_panel, 0)
        root.addLayout(body, 1)
        self.setCentralWidget(center)

        for index, (title, hint) in enumerate(_NAV_ITEMS):
            if index == 0 and self._facade is not None:
                self._stack.addWidget(CalibrationPage(self._facade))
            elif index == 1 and self._facade is not None:
                self._stack.addWidget(WorkflowPage(self._facade))
            elif index == 2 and self._facade is not None:
                self._stack.addWidget(MonitoringPage(self._facade))
            elif index == 3 and self._facade is not None:
                self._stack.addWidget(TemplatePage(self._facade))
            elif index == 4 and self._facade is not None:
                self._stack.addWidget(DashboardPage(self._facade))
            else:
                self._stack.addWidget(self._placeholder_page(title, hint))
        self._nav.currentRowChanged.connect(self._on_nav_changed)

    def _build_top_bar(self) -> QWidget:
        """构建顶部工具栏。

        Returns:
            顶部工具栏部件。
        """

        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        self._nav_toggle = QPushButton("☰")
        self._nav_toggle.setObjectName("Ghost")
        self._nav_toggle.setCheckable(True)
        self._nav_toggle.setChecked(True)
        self._nav_toggle.setToolTip("显示或隐藏导航栏")
        self._nav_toggle.toggled.connect(self._nav.setVisible)
        nav_font = self._nav_toggle.font()
        nav_font.setBold(True)
        self._nav_toggle.setFont(nav_font)
        layout.addWidget(self._nav_toggle)

        self._right_toggle = QPushButton("ⓘ")
        self._right_toggle.setObjectName("Ghost")
        self._right_toggle.setCheckable(True)
        self._right_toggle.setChecked(True)
        self._right_toggle.setToolTip("显示或隐藏系统状态面板")
        self._right_toggle.toggled.connect(self._right_panel.setVisible)
        info_font = self._right_toggle.font()
        info_font.setBold(True)
        self._right_toggle.setFont(info_font)

        layout.addStretch(1)
        layout.addWidget(self._right_toggle)
        return bar

    def _build_nav(self) -> QListWidget:
        """构建左侧导航。

        Returns:
            导航列表部件。
        """

        self._nav.setFixedWidth(200)
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

    def _build_right_panel(self) -> QWidget:
        """构建右侧系统状态栏。

        Returns:
            系统状态栏部件。
        """

        panel = QFrame()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel("系统状态")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self._context = QLabel(self._context_text("设备接入与校准"))
        self._context.setObjectName("PageHint")
        self._context.setWordWrap(True)
        layout.addWidget(self._context)
        import_btn = QPushButton("导入旧工作区")
        import_btn.setObjectName("Secondary")
        import_btn.clicked.connect(self._import_legacy_workspace)
        layout.addWidget(import_btn)
        layout.addStretch(1)
        return panel

    @staticmethod
    def _placeholder_page(title: str, hint: str) -> QWidget:
        """构建占位页面。

        Args:
            title: 页面标题。
            hint: 页面说明。

        Returns:
            占位页面部件。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        hint_label = QLabel(f"{hint}\n\n该页面将在后续批次接入具体功能。")
        hint_label.setObjectName("PageHint")
        hint_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addStretch(1)
        return page

    def _on_nav_changed(self, row: int) -> None:
        """切换当前页面。

        Args:
            row: 导航行号。
        """

        if row < 0:
            return
        self._stack.setCurrentIndex(row)
        page = self._stack.currentWidget()
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            on_show()
        title = _NAV_ITEMS[row][0]
        self._context.setText(self._context_text(title))
        self._logger.info("切换页面: %s", title)

    def _context_text(self, title: str) -> str:
        """生成右侧系统状态文本。

        Args:
            title: 当前页面标题。

        Returns:
            上下文状态文本。
        """

        if self._facade is None:
            return (
                f"当前页面: {title}\n"
                f"工作区: {self._settings.workspace_dir}\n"
                "状态: 已启动\n"
                "日志: 已启用"
            )
        status = self._facade.status()
        return (
            f"当前页面: {title}\n"
            f"工作区: {status.workspace_dir}\n"
            f"自动化: {status.automation_provider}\n"
            f"视觉: {status.vision_provider}\n"
            f"平台: {status.platform_provider}\n"
            f"AI 文字: {status.ai_text_provider}\n"
            f"AI 多模态: {status.ai_vision_provider}\n"
            "日志: 已启用"
        )

    def _restore_window_state(self) -> None:
        """恢复窗口尺寸和面板显示状态。"""

        default_width = 1440
        default_height = 900
        if not self._state_path.exists():
            self.resize(default_width, default_height)
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.resize(default_width, default_height)
            return
        self.resize(
            max(960, int(data.get("width", default_width))),
            max(680, int(data.get("height", default_height))),
        )
        self._nav_toggle.setChecked(bool(data.get("nav_visible", True)))
        self._right_toggle.setChecked(bool(data.get("right_visible", True)))
        if data.get("maximized"):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _save_window_state(self) -> None:
        """保存窗口尺寸和面板显示状态。"""

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        if self.isMinimized():
            return
        data = {
            "width": self.width(),
            "height": self.height(),
            "maximized": bool(self.windowState() & Qt.WindowState.WindowMaximized),
            "nav_visible": self._nav.isVisible(),
            "right_visible": self._right_panel.isVisible(),
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _import_legacy_workspace(self) -> None:
        """从旧 workspace 导入可兼容数据。"""

        if self._facade is None:
            return
        try:
            report = self._facade.import_legacy_workspace("workspace")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        message = (
            f"已导入锚点: {report.imported_anchors}\n"
            f"已导入工作流: {report.imported_workflows}\n"
            f"已导入模板: {report.imported_templates}\n"
            f"跳过文件: {len(report.skipped)}"
        )
        self._logger.info("旧工作区导入完成: %s", message.replace("\n", "; "))
        QMessageBox.information(self, "导入完成", message)
        page = self._stack.currentWidget()
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            on_show()
