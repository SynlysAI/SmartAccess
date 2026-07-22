"""系统设置页面。"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.spin_box import (
    FocusWheelDoubleSpinBox,
    FocusWheelSpinBox,
)
from smartaccess.desktop.widgets.table_style import NoWheelComboBox
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.config.settings import AppSettings


class SystemSettingsPage(QWidget):
    """编辑工作区用户级系统配置。"""

    def __init__(
        self,
        facade: RuntimeFacade,
        parent: QWidget | None = None,
    ) -> None:
        """初始化系统设置页面。

        Args:
            facade: 运行时门面。
            parent: Qt 父组件。
        """

        super().__init__(parent)
        self._facade = facade
        self._display_settings = AppSettings.from_env()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        hint = QLabel(
            "页面配置保存在 workspace/app_state/application_settings.json。"
            "操作系统环境变量优先级最高；服务连接类配置保存后需重启软件生效。"
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(self._build_general_section())
        content_layout.addWidget(self._build_execution_section())
        content_layout.addWidget(self._build_ocr_section())
        content_layout.addWidget(self._build_ai_section())
        content_layout.addWidget(self._build_platform_section())
        content_layout.addWidget(self._build_messaging_section())
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._state_label = QLabel()
        self._state_label.setObjectName("PageHint")
        self._state_label.setWordWrap(True)
        root.addWidget(self._state_label)
        self._fill_settings(self._display_settings)

    def on_show(self) -> None:
        """页面显示时重新读取当前配置。"""

        self._display_settings = AppSettings.from_env()
        self._fill_settings(self._display_settings)

    def _build_header(self) -> QHBoxLayout:
        """构建页面标题和操作按钮。"""

        layout = QHBoxLayout()
        title = QLabel("系统设置")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addStretch(1)

        open_button = QPushButton("打开配置目录")
        open_button.setObjectName("Secondary")
        open_button.clicked.connect(self._open_settings_directory)
        layout.addWidget(open_button)

        reset_button = QPushButton("恢复 .env 默认")
        reset_button.setObjectName("Secondary")
        reset_button.clicked.connect(self._reset_settings)
        layout.addWidget(reset_button)

        save_button = QPushButton("保存配置")
        save_button.clicked.connect(self._save_settings)
        layout.addWidget(save_button)
        return layout

    def _build_general_section(self) -> QWidget:
        """构建基础设置区域。"""

        panel, layout = self._section("基础设置")
        form = QFormLayout()
        self._workspace_dir = QLineEdit()
        workspace_editor = QWidget()
        workspace_layout = QHBoxLayout(workspace_editor)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(6)
        workspace_layout.addWidget(self._workspace_dir, 1)
        workspace_button = QPushButton("选择目录")
        workspace_button.setObjectName("Secondary")
        workspace_button.clicked.connect(self._select_workspace)
        workspace_layout.addWidget(workspace_button)
        self._log_level = self._combo(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._automation_provider = self._combo(["real", "stub"])
        self._device_id = QLineEdit()
        form.addRow("工作区", workspace_editor)
        form.addRow("日志级别", self._log_level)
        form.addRow("自动化 Provider", self._automation_provider)
        form.addRow("执行端设备 ID", self._device_id)
        layout.addLayout(form)
        return panel

    def _build_execution_section(self) -> QWidget:
        """构建动作和视觉校验默认值区域。"""

        panel, layout = self._section("动作与校验默认值")
        form = QFormLayout()
        self._default_action_wait = self._seconds_spin(0, 3600, 0.5)
        self._default_ocr_timeout = self._seconds_spin(0, 3600, 1.0)
        self._default_ocr_poll_interval = self._seconds_spin(0.1, 60, 0.1)
        self._default_precheck_threshold = FocusWheelDoubleSpinBox()
        self._default_precheck_threshold.setRange(0, 1)
        self._default_precheck_threshold.setDecimals(2)
        self._default_precheck_threshold.setSingleStep(0.05)
        form.addRow("动作后等待", self._default_action_wait)
        form.addRow("OCR 识别超时", self._default_ocr_timeout)
        form.addRow("OCR 轮询间隔", self._default_ocr_poll_interval)
        form.addRow("执行前图像相似度", self._default_precheck_threshold)
        explanation = QLabel(
            "动作等待与 OCR 参数用于新建工作流步骤；执行前图像相似度会在"
            "新建或重新保存锚点配置时应用，未重新保存的配置保持原值。"
        )
        explanation.setObjectName("PageHint")
        explanation.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(explanation)
        return panel

    def _build_ocr_section(self) -> QWidget:
        """构建 OCR 服务设置区域。"""

        panel, layout = self._section("OCR 服务")
        form = QFormLayout()
        self._ocr_mode = self._combo(
            ["local", "paddleocr-vl", "paddlex", "stub"],
        )
        self._ocr_api_url = QLineEdit()
        self._ocr_api_url.setPlaceholderText("http://127.0.0.1:8090")
        form.addRow("OCR 模式", self._ocr_mode)
        form.addRow("OCR API 地址", self._ocr_api_url)
        layout.addLayout(form)
        return panel

    def _build_ai_section(self) -> QWidget:
        """构建文字与多模态 AI 设置区域。"""

        panel, layout = self._section("AI 服务")
        text_title = QLabel("文字模型（工作流生成）")
        text_title.setObjectName("PageHint")
        layout.addWidget(text_title)
        text_form = QFormLayout()
        self._ai_text_provider = self._combo(
            ["template", "deepseek", "codex", "qwen"],
        )
        self._ai_text_base_url = QLineEdit()
        self._ai_text_model = QLineEdit()
        self._ai_text_api_key = self._password_edit()
        self._ai_text_timeout = self._seconds_spin(1, 3600, 5)
        text_form.addRow("Provider", self._ai_text_provider)
        text_form.addRow("Base URL", self._ai_text_base_url)
        text_form.addRow("模型", self._ai_text_model)
        text_form.addRow("API Key", self._ai_text_api_key)
        text_form.addRow("请求超时", self._ai_text_timeout)
        layout.addLayout(text_form)

        vision_title = QLabel("多模态模型（AI 辅助接入）")
        vision_title.setObjectName("PageHint")
        layout.addWidget(vision_title)
        vision_form = QFormLayout()
        self._ai_vision_provider = self._combo(
            ["template", "codex", "qwen", "deepseek"],
        )
        self._ai_vision_base_url = QLineEdit()
        self._ai_vision_model = QLineEdit()
        self._ai_vision_api_key = self._password_edit()
        self._ai_vision_timeout = self._seconds_spin(1, 3600, 5)
        self._ai_vision_thinking = QCheckBox("启用模型思考模式")
        vision_form.addRow("Provider", self._ai_vision_provider)
        vision_form.addRow("Base URL", self._ai_vision_base_url)
        vision_form.addRow("模型", self._ai_vision_model)
        vision_form.addRow("API Key", self._ai_vision_api_key)
        vision_form.addRow("请求超时", self._ai_vision_timeout)
        vision_form.addRow("思考模式", self._ai_vision_thinking)
        layout.addLayout(vision_form)
        return panel

    def _build_platform_section(self) -> QWidget:
        """构建平台连接设置区域。"""

        panel, layout = self._section("SpecLabOS 平台")
        form = QFormLayout()
        self._platform_provider = self._combo(["real", "stub"])
        self._speclabos_base_url = QLineEdit()
        self._speclabos_api_key = self._password_edit()
        self._speclabos_datahub_key = self._password_edit()
        self._speclabos_timeout = self._seconds_spin(1, 3600, 5)
        form.addRow("平台 Provider", self._platform_provider)
        form.addRow("平台地址", self._speclabos_base_url)
        form.addRow("平台 API Key", self._speclabos_api_key)
        form.addRow("DataHub Key", self._speclabos_datahub_key)
        form.addRow("请求超时", self._speclabos_timeout)
        layout.addLayout(form)
        return panel

    def _build_messaging_section(self) -> QWidget:
        """构建 RabbitMQ 与本地接口高级设置区域。"""

        panel, layout = self._section("高级网络与消息服务")
        form = QFormLayout()
        self._rabbitmq_enabled = QCheckBox("启用 RabbitMQ 远程任务")
        self._rabbitmq_host = QLineEdit()
        self._rabbitmq_port = self._port_spin()
        self._rabbitmq_username = QLineEdit()
        self._rabbitmq_password = self._password_edit()
        self._edge_api_host = QLineEdit()
        self._edge_api_port = self._port_spin()
        self._udp_host = QLineEdit()
        self._udp_port = self._port_spin()
        self._udp_timeout = self._seconds_spin(0.1, 3600, 1)
        form.addRow("RabbitMQ", self._rabbitmq_enabled)
        form.addRow("RabbitMQ 主机", self._rabbitmq_host)
        form.addRow("RabbitMQ 端口", self._rabbitmq_port)
        form.addRow("RabbitMQ 用户名", self._rabbitmq_username)
        form.addRow("RabbitMQ 密码", self._rabbitmq_password)
        form.addRow("Edge API 主机", self._edge_api_host)
        form.addRow("Edge API 端口", self._edge_api_port)
        form.addRow("UDP 主机", self._udp_host)
        form.addRow("UDP 端口", self._udp_port)
        form.addRow("UDP 超时", self._udp_timeout)
        layout.addLayout(form)
        return panel

    def _fill_settings(self, settings: AppSettings) -> None:
        """将配置对象回填到页面控件。

        Args:
            settings: 当前配置对象。
        """

        self._workspace_dir.setText(str(settings.workspace_dir.resolve()))
        self._set_combo(self._log_level, settings.log_level)
        self._set_combo(self._automation_provider, settings.automation_provider)
        self._device_id.setText(settings.device_id)
        self._default_action_wait.setValue(settings.default_action_wait_seconds)
        self._default_ocr_timeout.setValue(settings.default_ocr_timeout_seconds)
        self._default_ocr_poll_interval.setValue(
            settings.default_ocr_poll_interval_seconds
        )
        self._default_precheck_threshold.setValue(
            settings.default_precheck_image_threshold
        )
        self._set_combo(self._ocr_mode, settings.ocr_mode)
        self._ocr_api_url.setText(settings.ocr_api_url)
        self._set_combo(self._ai_text_provider, settings.ai_text_provider)
        self._ai_text_base_url.setText(settings.ai_text_base_url)
        self._ai_text_model.setText(settings.ai_text_model)
        self._ai_text_api_key.setText(settings.ai_text_api_key or "")
        self._ai_text_timeout.setValue(settings.ai_text_timeout_seconds)
        self._set_combo(self._ai_vision_provider, settings.ai_vision_provider)
        self._ai_vision_base_url.setText(settings.ai_vision_base_url)
        self._ai_vision_model.setText(settings.ai_vision_model)
        self._ai_vision_api_key.setText(settings.ai_vision_api_key or "")
        self._ai_vision_timeout.setValue(settings.ai_vision_timeout_seconds)
        self._ai_vision_thinking.setChecked(settings.ai_vision_enable_thinking)
        self._set_combo(self._platform_provider, settings.platform_provider)
        self._speclabos_base_url.setText(settings.speclabos_base_url or "")
        self._speclabos_api_key.setText(settings.speclabos_api_key or "")
        self._speclabos_datahub_key.setText(settings.speclabos_datahub_key or "")
        self._speclabos_timeout.setValue(settings.speclabos_timeout_seconds)
        self._rabbitmq_enabled.setChecked(settings.rabbitmq_enabled)
        self._rabbitmq_host.setText(settings.rabbitmq_host)
        self._rabbitmq_port.setValue(settings.rabbitmq_port)
        self._rabbitmq_username.setText(settings.rabbitmq_username)
        self._rabbitmq_password.setText(settings.rabbitmq_password)
        self._edge_api_host.setText(settings.edge_api_host)
        self._edge_api_port.setValue(settings.edge_api_port)
        self._udp_host.setText(settings.udp_host)
        self._udp_port.setValue(settings.udp_port)
        self._udp_timeout.setValue(settings.udp_timeout_seconds)
        self._state_label.setText(
            f"当前用户配置文件：{settings.user_settings_path(settings.workspace_dir)}"
        )

    def _collect_overrides(self) -> dict[str, str]:
        """收集页面配置并转换为环境变量键值。"""

        ocr_mode = self._combo_text(self._ocr_mode)
        vision_provider = (
            "local"
            if ocr_mode == "local"
            else "stub"
            if ocr_mode == "stub"
            else "api"
        )
        return {
            "SMARTACCESS_LOG_LEVEL": self._combo_text(self._log_level),
            "SMARTACCESS_AUTOMATION_PROVIDER": self._combo_text(
                self._automation_provider
            ),
            "SMARTACCESS_DEVICE_ID": self._device_id.text().strip(),
            "SMARTACCESS_DEFAULT_ACTION_WAIT_SECONDS": str(
                self._default_action_wait.value()
            ),
            "SMARTACCESS_DEFAULT_OCR_TIMEOUT_SECONDS": str(
                self._default_ocr_timeout.value()
            ),
            "SMARTACCESS_DEFAULT_OCR_POLL_INTERVAL_SECONDS": str(
                self._default_ocr_poll_interval.value()
            ),
            "SMARTACCESS_DEFAULT_PRECHECK_IMAGE_THRESHOLD": str(
                self._default_precheck_threshold.value()
            ),
            "SMARTACCESS_OCR_MODE": ocr_mode,
            "SMARTACCESS_OCR_API_URL": self._ocr_api_url.text().strip(),
            "SMARTACCESS_VISION_PROVIDER": vision_provider,
            "SMARTACCESS_VISION_API_URL": self._ocr_api_url.text().strip(),
            "SMARTACCESS_AI_TEXT_PROVIDER": self._combo_text(
                self._ai_text_provider
            ),
            "SMARTACCESS_AI_TEXT_BASE_URL": self._ai_text_base_url.text().strip(),
            "SMARTACCESS_AI_TEXT_MODEL": self._ai_text_model.text().strip(),
            "SMARTACCESS_AI_TEXT_API_KEY": self._ai_text_api_key.text().strip(),
            "SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS": str(
                self._ai_text_timeout.value()
            ),
            "SMARTACCESS_AI_VISION_PROVIDER": self._combo_text(
                self._ai_vision_provider
            ),
            "SMARTACCESS_AI_VISION_BASE_URL": (
                self._ai_vision_base_url.text().strip()
            ),
            "SMARTACCESS_AI_VISION_MODEL": self._ai_vision_model.text().strip(),
            "SMARTACCESS_AI_VISION_API_KEY": self._ai_vision_api_key.text().strip(),
            "SMARTACCESS_AI_VISION_TIMEOUT_SECONDS": str(
                self._ai_vision_timeout.value()
            ),
            "SMARTACCESS_AI_VISION_ENABLE_THINKING": self._bool_text(
                self._ai_vision_thinking.isChecked()
            ),
            "SMARTACCESS_PLATFORM_PROVIDER": self._combo_text(
                self._platform_provider
            ),
            "SPECLABOS_BASE_URL": self._speclabos_base_url.text().strip(),
            "SPECLABOS_API_KEY": self._speclabos_api_key.text().strip(),
            "SPECLABOS_DATAHUB_KEY": self._speclabos_datahub_key.text().strip(),
            "SPECLABOS_TIMEOUT_SECONDS": str(self._speclabos_timeout.value()),
            "SMARTACCESS_RABBITMQ_ENABLED": self._bool_text(
                self._rabbitmq_enabled.isChecked()
            ),
            "SMARTACCESS_RABBITMQ_HOST": self._rabbitmq_host.text().strip(),
            "SMARTACCESS_RABBITMQ_PORT": str(self._rabbitmq_port.value()),
            "SMARTACCESS_RABBITMQ_USERNAME": self._rabbitmq_username.text().strip(),
            "SMARTACCESS_RABBITMQ_PASSWORD": self._rabbitmq_password.text(),
            "SMARTACCESS_EDGE_API_HOST": self._edge_api_host.text().strip(),
            "SMARTACCESS_EDGE_API_PORT": str(self._edge_api_port.value()),
            "SMARTACCESS_UDP_HOST": self._udp_host.text().strip(),
            "SMARTACCESS_UDP_PORT": str(self._udp_port.value()),
            "SMARTACCESS_UDP_TIMEOUT_SECONDS": str(self._udp_timeout.value()),
        }

    def _save_settings(self) -> None:
        """保存用户配置并更新当前进程可立即使用的默认值。"""

        workspace_text = self._workspace_dir.text().strip()
        if not workspace_text:
            QMessageBox.warning(self, "保存配置失败", "请选择有效的工作区目录。")
            return
        workspace_dir = Path(workspace_text).expanduser()
        try:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            AppSettings.save_env_value(
                "SMARTACCESS_WORKSPACE_DIR",
                str(workspace_dir.resolve()),
            )
            path = AppSettings.save_user_overrides(
                workspace_dir,
                self._collect_overrides(),
            )
            self._display_settings = AppSettings.from_env()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存配置失败", str(exc))
            return
        self._apply_runtime_defaults(self._display_settings)
        self._fill_settings(self._display_settings)
        self._state_label.setText(f"配置已保存：{path}；服务连接配置重启后生效。")
        QMessageBox.information(
            self,
            "配置已保存",
            "页面中新建动作与手工校验的默认值已立即生效。"
            "AI 生成、OCR、平台和消息服务配置将在重启软件后生效。",
        )

    def _reset_settings(self) -> None:
        """清除用户覆盖配置并回退到 .env。"""

        reply = QMessageBox.question(
            self,
            "恢复 .env 默认",
            "确定删除当前工作区的系统设置覆盖并恢复 .env 配置吗？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            AppSettings.clear_user_overrides(self._facade.workspace_dir())
            self._display_settings = AppSettings.from_env()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "恢复配置失败", str(exc))
            return
        self._apply_runtime_defaults(self._display_settings)
        self._fill_settings(self._display_settings)
        self._state_label.setText("已清除用户配置，当前页面恢复为 .env 与内置默认值。")

    def _apply_runtime_defaults(self, settings: AppSettings) -> None:
        """把无需重建 Provider 的默认值更新到当前进程。

        Args:
            settings: 重新加载后的配置。
        """

        current = self._facade.settings()
        current.default_action_wait_seconds = settings.default_action_wait_seconds
        current.default_ocr_timeout_seconds = settings.default_ocr_timeout_seconds
        current.default_ocr_poll_interval_seconds = (
            settings.default_ocr_poll_interval_seconds
        )
        current.default_precheck_image_threshold = (
            settings.default_precheck_image_threshold
        )

    def _open_settings_directory(self) -> None:
        """在系统文件管理器中打开配置目录。"""

        workspace_text = self._workspace_dir.text().strip()
        workspace_dir = (
            Path(workspace_text).expanduser()
            if workspace_text
            else self._facade.workspace_dir()
        )
        path = AppSettings.user_settings_path(workspace_dir).parent
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _select_workspace(self) -> None:
        """打开目录选择器并回填工作区路径。"""

        current = self._workspace_dir.text().strip() or str(
            self._facade.workspace_dir()
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 SmartAccess 工作区",
            current,
        )
        if selected:
            self._workspace_dir.setText(str(Path(selected).resolve()))

    @staticmethod
    def _section(title: str) -> tuple[QWidget, QVBoxLayout]:
        """创建统一样式的设置分组。

        Args:
            title: 分组标题。

        Returns:
            分组面板和内容布局。
        """

        panel, layout = create_card(margins=(16, 14, 16, 14), spacing=10)
        title_label = QLabel(title)
        title_label.setObjectName("PageHint")
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        return panel, layout

    @staticmethod
    def _combo(values: list[str], *, editable: bool = False) -> NoWheelComboBox:
        """创建系统设置下拉框。

        Args:
            values: 可选值列表。
            editable: 是否允许输入自定义值。

        Returns:
            已初始化的下拉框。
        """

        combo = NoWheelComboBox()
        combo.setEditable(editable)
        for value in values:
            combo.addItem(value, value)
        return combo

    @staticmethod
    def _seconds_spin(
        minimum: float,
        maximum: float,
        step: float,
    ) -> FocusWheelDoubleSpinBox:
        """创建秒数输入框。

        Args:
            minimum: 最小秒数。
            maximum: 最大秒数。
            step: 单次调整步长。

        Returns:
            已初始化的秒数输入框。
        """

        spin = FocusWheelDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(step)
        spin.setSuffix(" s")
        return spin

    @staticmethod
    def _port_spin() -> FocusWheelSpinBox:
        """创建网络端口输入框。"""

        spin = FocusWheelSpinBox()
        spin.setRange(1, 65535)
        return spin

    @staticmethod
    def _password_edit() -> QLineEdit:
        """创建密码掩码输入框。"""

        editor = QLineEdit()
        editor.setEchoMode(QLineEdit.EchoMode.Password)
        return editor

    @staticmethod
    def _set_combo(combo: NoWheelComboBox, value: str) -> None:
        """设置下拉框当前值。

        Args:
            combo: 目标下拉框。
            value: 待设置值。
        """

        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif value:
            combo.addItem(value, value)
            combo.setCurrentIndex(combo.count() - 1)

    @staticmethod
    def _combo_text(combo: NoWheelComboBox) -> str:
        """返回下拉框当前文本。

        Args:
            combo: 目标下拉框。

        Returns:
            清理后的当前值。
        """

        return combo.currentText().strip()

    @staticmethod
    def _bool_text(value: bool) -> str:
        """把布尔值转换为配置文件文本。

        Args:
            value: 布尔值。

        Returns:
            小写布尔文本。
        """

        return "true" if value else "false"
