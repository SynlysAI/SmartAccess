"""SmartAccess 主窗口。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
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

from smartaccess import APP_NAME, RELEASE_CHANNEL, RELEASE_DATE, VERSION_DISPLAY
from smartaccess.desktop.pages.calibration_page import CalibrationPage
from smartaccess.desktop.pages.data_collection_page import DataCollectionPage
from smartaccess.desktop.pages.dashboard_page import DashboardPage
from smartaccess.desktop.pages.monitoring_page import MonitoringPage
from smartaccess.desktop.pages.settings_page import SystemSettingsPage
from smartaccess.desktop.pages.template_page import TemplatePage
from smartaccess.desktop.pages.workflow_page import WorkflowPage
from smartaccess.desktop.shell.tray import TrayController
from smartaccess.desktop.viewmodels.base import EventRelay
from smartaccess.shared.config.settings import AppSettings
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.events.bus import RuntimeEvent
from smartaccess.shared.events.runtime import RuntimeEventName
from smartaccess.shared.logging import get_logger

_NAV_ITEMS = [
    ("设备接入与校准", "窗口扫描、截图、ROI 和锚点配置"),
    ("工作流设计", "生成、编辑、检查和保存工作流"),
    ("运行监控", "执行工作流并查看日志和审计"),
    ("模板/平台", "模板发布、回滚和平台同步"),
    ("运行概览", "设备、模板、运行和异常概览"),
    ("数据采集", "配置本地目录监听并可靠上传至 SmartDataHub"),
    ("系统设置", "配置 OCR、AI、平台、默认参数和消息服务"),
]

# 触发运行结束提醒的终态事件
_TERMINAL_EVENT_NAMES = {
    RuntimeEventName.RUN_COMPLETED,
    RuntimeEventName.RUN_FAILED,
    RuntimeEventName.RUN_CANCELLED,
}


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

        self.setWindowTitle(f"{APP_NAME} {VERSION_DISPLAY}")
        self.setMinimumSize(800, 500)
        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        self._stack = QStackedWidget()
        self._right_panel = self._build_right_panel()
        # 系统状态信息低频参考，默认收起把宽度让给主内容区，由顶栏 ⓘ 切换。
        self._right_panel.hide()
        self._monitoring_page: MonitoringPage | None = None
        self._data_collection_page = None
        self._run_started_at: dict[str, datetime] = {}
        self._quitting = False
        self._tray_hint_shown = False

        self._build_ui()
        self._restore_window_state()
        self._nav.setCurrentRow(0)
        self._build_tray()
        self._subscribe_runtime_events()
        self._logger.info("主窗口初始化完成")

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭窗口时最小化到托盘；真正退出时保存 UI 状态。"""

        if self._tray is not None and not self._quitting:
            # 有关闭到托盘能力：点 X 只是隐藏窗口，后台继续运行
            event.ignore()
            self._save_window_state()
            self.hide()
            if not self._tray_hint_shown:
                self._tray.show_message(
                    APP_NAME,
                    "SmartAccess 已最小化到系统托盘，"
                    "云端任务与数据采集监听将继续在后台运行。",
                )
                self._tray_hint_shown = True
            return
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self._save_window_state()
        super().closeEvent(event)
        # 全局关闭了"最后一个窗口即退出"，此处需显式退出应用
        QApplication.quit()

    def _build_tray(self) -> None:
        """创建系统托盘并连接还原和退出动作。"""

        self._tray = TrayController(self.windowIcon(), self)
        if not self._tray.available:
            self._tray = None
            return
        self._tray.restore_requested.connect(self.show_and_activate)
        self._tray.quit_requested.connect(self._quit_from_tray)

    def _subscribe_runtime_events(self) -> None:
        """订阅运行时事件用于运行结束提醒。"""

        if self._facade is None:
            return
        self._relay = EventRelay(self._facade, self)
        self._relay.event_received.connect(self._on_runtime_event)

    def show_and_activate(self) -> None:
        """还原并前置主窗口。"""

        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        """托盘退出入口：有活跃运行或采集监听时先确认再退出。"""

        if self._confirm_quit_with_active_work():
            return
        self._quitting = True
        self.close()
        QApplication.quit()

    def _confirm_quit_with_active_work(self) -> bool:
        """存在活跃运行会话或采集监听时弹窗确认退出。

        Returns:
            用户取消退出时返回 True。
        """

        active = []
        if self._facade is not None:
            active = [
                session
                for session in self._facade.list_sessions()
                if session.status.value
                in {"created", "ready", "running", "blocked", "stopping"}
            ]
        collecting = (
            self._data_collection_page is not None
            and self._data_collection_page.is_collecting()
        )
        if not active and not collecting:
            return False
        reasons = []
        if active:
            reasons.append(f"{len(active)} 个正在运行或等待确认的会话")
        if collecting:
            reasons.append("数据采集监听正在运行")
        reply = QMessageBox.question(
            self,
            "退出确认",
            (
                f"当前有{'、'.join(reasons)}，"
                "退出后将中止这些任务。\n\n确认退出 SmartAccess？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply != QMessageBox.StandardButton.Yes

    def _on_runtime_event(self, event: RuntimeEvent) -> None:
        """处理运行时事件，对本地发起的运行做结束提醒。

        Args:
            event: 运行时事件。
        """

        session_id = event.session_id
        if not session_id:
            return
        if event.name == RuntimeEventName.RUN_STARTED:
            self._run_started_at[session_id] = event.timestamp
            return
        if event.name not in _TERMINAL_EVENT_NAMES:
            return
        started = self._run_started_at.pop(session_id, None)
        if self._facade is None:
            return
        session = self._facade.get_session(session_id)
        if session is None or session.trigger_source != "local":
            # 云端远程发起的运行不在电脑前，结果由云端任务详情展示
            return
        elapsed = self._format_elapsed(started, event.timestamp)
        if event.name == RuntimeEventName.RUN_FAILED:
            self._notify_run_failed(event, session, elapsed)
        else:
            self._notify_run_finished(event, session, elapsed)

    def _notify_run_finished(
        self,
        event: RuntimeEvent,
        session,
        elapsed: str,
    ) -> None:
        """本地运行完成或取消时发送轻提醒。

        Args:
            event: 终态运行时事件。
            session: 运行会话。
            elapsed: 格式化耗时。
        """

        label = "运行完成" if event.name == RuntimeEventName.RUN_COMPLETED else "运行已取消"
        QApplication.alert(self)
        if self._tray is not None:
            self._tray.show_message(
                f"{label}: {session.workflow_id}",
                f"耗时 {elapsed}\n会话: {session.session_id}",
            )
        self._logger.info(
            "[运行提醒] %s | workflow=%s session=%s elapsed=%s",
            label,
            session.workflow_id,
            session.session_id,
            elapsed,
        )

    def _notify_run_failed(
        self,
        event: RuntimeEvent,
        session,
        elapsed: str,
    ) -> None:
        """本地运行失败时切回主窗口并弹置顶告警。

        Args:
            event: 终态运行时事件。
            session: 运行会话。
            elapsed: 格式化耗时。
        """

        payload = event.payload
        error = str(payload.get("error") or payload.get("detail") or "-")
        step_id = str(payload.get("step_id") or "-")
        self._logger.info(
            "[运行提醒] 运行失败 | workflow=%s session=%s step=%s error=%s",
            session.workflow_id,
            session.session_id,
            step_id,
            error,
        )
        QApplication.alert(self)
        self.show_and_activate()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("运行失败")
        box.setText(
            f"工作流 {session.workflow_id} 运行失败。\n\n"
            f"失败步骤: {step_id}\n"
            f"耗时: {elapsed}\n"
            f"会话: {session.session_id}\n\n"
            f"失败原因:\n{error}"
        )
        for label in box.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        view_button = box.addButton(
            "查看运行日志",
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.exec()
        if box.clickedButton() is view_button:
            self._open_monitoring_session(session.session_id)

    def _open_monitoring_session(self, session_id: str) -> None:
        """切到运行监控页并选中指定会话。

        Args:
            session_id: 运行会话 ID。
        """

        for row, (title, _hint) in enumerate(_NAV_ITEMS):
            if title == "运行监控":
                self._nav.setCurrentRow(row)
                break
        if self._monitoring_page is not None:
            self._monitoring_page.select_session(session_id)

    @staticmethod
    def _format_elapsed(started: datetime | None, ended: datetime) -> str:
        """格式化运行耗时。

        Args:
            started: 运行开始时间；缺失时返回占位符。
            ended: 终态事件时间。

        Returns:
            形如 "3分25秒" 的耗时文本。
        """

        if started is None:
            return "-"
        seconds = max(0, int((ended - started).total_seconds()))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}小时{minutes}分{secs}秒"
        if minutes:
            return f"{minutes}分{secs}秒"
        return f"{secs}秒"


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
        nav_panel = self._build_nav()
        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(nav_panel, 0)
        body.addWidget(self._stack, 1)
        body.addWidget(self._right_panel, 0)
        root.addLayout(body, 1)
        self.setCentralWidget(center)

        for title, hint in _NAV_ITEMS:
            if title == "设备接入与校准" and self._facade is not None:
                self._stack.addWidget(CalibrationPage(self._facade))
            elif title == "数据采集" and self._facade is not None:
                self._data_collection_page = DataCollectionPage(self._facade)
                self._stack.addWidget(self._data_collection_page)
            elif title == "工作流设计" and self._facade is not None:
                self._stack.addWidget(WorkflowPage(self._facade))
            elif title == "运行监控" and self._facade is not None:
                self._monitoring_page = MonitoringPage(self._facade)
                self._stack.addWidget(self._monitoring_page)
            elif title == "模板/平台" and self._facade is not None:
                self._stack.addWidget(TemplatePage(self._facade))
            elif title == "运行概览" and self._facade is not None:
                self._stack.addWidget(DashboardPage(self._facade))
            elif title == "系统设置" and self._facade is not None:
                self._stack.addWidget(SystemSettingsPage(self._facade))
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
        self._nav_toggle.toggled.connect(self._nav_panel.setVisible)
        nav_font = self._nav_toggle.font()
        nav_font.setBold(True)
        self._nav_toggle.setFont(nav_font)
        layout.addWidget(self._nav_toggle)

        self._right_toggle = QPushButton("ⓘ")
        self._right_toggle.setObjectName("Ghost")
        self._right_toggle.setCheckable(True)
        self._right_toggle.setChecked(False)
        self._right_toggle.setToolTip("显示或隐藏系统状态面板")
        self._right_toggle.toggled.connect(self._right_panel.setVisible)
        info_font = self._right_toggle.font()
        info_font.setBold(True)
        self._right_toggle.setFont(info_font)

        layout.addStretch(1)
        user_text = self._user_text()
        if user_text:
            user_label = QLabel(user_text)
            user_label.setObjectName("PageHint")
            user_label.setToolTip(user_text)
            layout.addWidget(user_label)
        layout.addWidget(self._right_toggle)
        return bar

    def _user_text(self) -> str:
        """生成顶部登录用户文本。

        Returns:
            登录用户展示文本；未登录时返回空字符串。
        """

        username = self._settings.speclabos_username.strip()
        if not username:
            return ""
        role = self._settings.speclabos_user_role.strip()
        return f"{username} · {role}" if role else username

    def _show_about(self) -> None:
        """显示 SmartAccess 版本和发布信息。"""

        QMessageBox.about(
            self,
            f"关于 {APP_NAME}",
            (
                f"{APP_NAME}\n\n"
                f"版本：{VERSION_DISPLAY}\n"
                f"发布阶段：{RELEASE_CHANNEL}\n"
                f"发布日期：{RELEASE_DATE}\n\n"
                "首个功能完善的内部测试版本。"
            ),
        )

    def _build_nav(self) -> QWidget:
        """构建左侧导航。

        Returns:
            包含导航列表和版本入口的导航面板。
        """

        panel = QFrame()
        panel.setObjectName("NavPanel")
        panel.setFixedWidth(200)
        self._nav_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        self._nav.setIconSize(QSize(18, 18))
        icons = [
            QStyle.StandardPixmap.SP_ComputerIcon,
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            QStyle.StandardPixmap.SP_MediaPlay,
            QStyle.StandardPixmap.SP_DirIcon,
            QStyle.StandardPixmap.SP_FileDialogInfoView,
            QStyle.StandardPixmap.SP_DriveHDIcon,
        ]
        for index, (title, hint) in enumerate(_NAV_ITEMS):
            item = QListWidgetItem(title)
            if title == "系统设置":
                item.setIcon(self._settings_icon())
            else:
                item.setIcon(self.style().standardIcon(icons[index]))
            item.setToolTip(hint)
            self._nav.addItem(item)
        layout.addWidget(self._nav, 1)

        version_button = QPushButton(VERSION_DISPLAY)
        version_button.setObjectName("VersionButton")
        version_button.setCursor(Qt.CursorShape.PointingHandCursor)
        version_button.setToolTip(f"查看关于 {APP_NAME}")
        version_button.clicked.connect(self._show_about)
        layout.addWidget(
            version_button,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        )
        return panel

    def _settings_icon(self) -> QIcon:
        """创建与导航栏尺寸一致的齿轮设置图标。"""

        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(self.palette().text().color())
        painter.setFont(QFont("Segoe UI Symbol", 14))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "⚙")
        painter.end()
        return QIcon(pixmap)

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
                f"执行端: {self._settings.device_id or '未配置'}\n"
                f"登录用户: {self._settings.speclabos_username or '未登录'}\n"
                "状态: 已启动\n"
                "日志: 已启用"
            )
        status = self._facade.status()
        return (
            f"当前页面: {title}\n"
            f"工作区: {status.workspace_dir}\n"
            f"执行端: {self._settings.device_id or '未配置'}\n"
            f"登录用户: {self._settings.speclabos_username or '未登录'}\n"
            f"自动化: {status.automation_provider}\n"
            f"OCR: {status.ocr_mode}\n"
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
        # 键名升级为 right_visible_v2：存量状态一次性迁移为默认隐藏，此后记住用户选择。
        self._right_toggle.setChecked(bool(data.get("right_visible_v2", False)))
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
            "nav_visible": self._nav_panel.isVisible(),
            "right_visible_v2": self._right_panel.isVisible(),
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
