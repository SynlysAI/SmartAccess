"""Qt 应用启动。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.logging import get_logger


def _resolve_icon_path() -> Path | None:
    """解析应用图标路径，兼容开发环境和 PyInstaller/Nuitka 打包。

    Returns:
        图标文件路径；未找到时返回 None。
    """

    candidates: list[Path] = []

    # PyInstaller onefile 打包：sys._MEIPASS 指向临时解压目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "resource" / "icon.png")

    # Nuitka standalone / PyInstaller 目录模式：可执行文件同级 resource 目录
    candidates.append(Path(sys.argv[0]).resolve().parent / "resource" / "icon.png")

    # 开发环境：从源文件路径向上查找项目根目录
    candidates.append(Path(__file__).resolve().parents[4] / "resource" / "icon.png")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_app_icon() -> QIcon | None:
    """加载桌面应用图标。

    Returns:
        图标对象；图标文件不存在或无效时返回 None。
    """

    icon_path = _resolve_icon_path()
    if icon_path is None:
        return None
    icon = QIcon(str(icon_path))
    return icon if not icon.isNull() else None


def _set_windows_app_id() -> None:
    """设置 Windows 任务栏应用 ID。"""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SmartAccess.Desktop"
        )
    except Exception:  # noqa: BLE001 - 图标归组失败不应阻断启动
        return


def _http_post_json(
    url: str,
    payload: dict,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
) -> dict:
    """发送 JSON POST 请求。

    Args:
        url: 请求地址。
        payload: JSON 请求体。
        timeout: 超时秒数。
        headers: 可选 HTTP 头。

    Returns:
        JSON 响应字典。
    """

    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = Request(
        url,
        data=body,
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}")
    except URLError as exc:
        raise RuntimeError(f"无法连接: {exc.reason}")


def _register_smartaccess_node(settings: AppSettings, token: str) -> None:
    """登录后注册并校验当前 SmartAccess 执行端。

    Args:
        settings: 应用配置。
        token: 登录成功后获得的 SpecLabOS 访问令牌。
    """

    if not settings.device_id:
        raise RuntimeError("未配置 SMARTACCESS_DEVICE_ID，请先在 .env 中配置唯一执行端 ID。")

    from urllib.error import HTTPError, URLError
    import json

    from smartaccess.bootstrap.heartbeat import (
        build_device_info,
        build_machine_fingerprint,
    )

    base_url = (settings.speclabos_base_url or "").rstrip("/")
    payload = {
        "node_id": settings.device_id,
        "machine_fingerprint": build_machine_fingerprint(settings),
        "device_info": build_device_info(settings),
    }
    try:
        _http_post_json(
            f"{base_url}/api/smartaccess/nodes/register",
            payload,
            timeout=settings.speclabos_timeout_seconds,
            headers={"Authorization": f"Bearer {token}"},
        )
    except RuntimeError as exc:
        text = str(exc)
        if "HTTP 409" not in text:
            raise
        raise RuntimeError(
            "当前 SMARTACCESS_DEVICE_ID 已被另一台电脑注册。\n\n"
            f"冲突 ID：{settings.device_id}\n"
            "请修改 .env 中的 SMARTACCESS_DEVICE_ID 后重新登录，"
            "例如 pc-用户名-机器名。"
        ) from exc
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"执行端注册检查失败: {exc}") from exc


def show_login_dialog(settings: AppSettings) -> bool:
    """显示 SpecLabOS 统一门户登录框。

    Args:
        settings: 应用配置。

    Returns:
        登录成功返回 True。
    """

    if not settings.speclabos_base_url:
        get_logger().info("未配置 SPECLABOS_BASE_URL，跳过统一门户登录")
        return True

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    _set_windows_app_id()
    app.setApplicationDisplayName("SmartAccess")
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    from smartaccess.desktop.shell.theme import apply_theme
    apply_theme(app)

    dialog = QDialog()
    dialog.setWindowTitle("SmartAccess 登录")
    dialog.setModal(True)
    dialog.setMinimumWidth(420)
    dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    if icon is not None:
        dialog.setWindowIcon(icon)

    username_edit = QLineEdit()
    username_edit.setPlaceholderText("请输入统一门户用户名")
    username_edit.setClearButtonEnabled(True)

    password_edit = QLineEdit()
    password_edit.setEchoMode(QLineEdit.EchoMode.Password)
    password_edit.setPlaceholderText("请输入密码")

    status_label = QLabel("")
    status_label.setObjectName("PageHint")
    status_label.setWordWrap(True)

    login_btn = QPushButton("登录")
    login_btn.setDefault(True)

    # ---- 构建 UI ----
    root = QVBoxLayout(dialog)
    root.setContentsMargins(28, 28, 28, 28)
    root.setSpacing(18)

    # 头部
    header = QWidget()
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(6)
    title_label = QLabel("SmartAccess")
    title_label.setObjectName("AppTitle")
    header_layout.addWidget(title_label)
    header_layout.addWidget(QLabel("实验室桌面执行端"))
    root.addWidget(header)

    # 卡片
    card = QFrame()
    card.setObjectName("Card")
    form = QVBoxLayout(card)
    form.setContentsMargins(22, 20, 22, 22)
    form.setSpacing(12)
    tip = QLabel("使用 SpecLabOS 统一门户账号登录 SmartAccess")
    tip.setObjectName("PageHint")
    tip.setWordWrap(True)
    form.addWidget(tip)

    def _field(label_text: str, editor: QLineEdit) -> QWidget:
        """构建表单字段。"""
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        lbl = QLabel(label_text)
        lbl.setObjectName("SectionTitle")
        layout.addWidget(lbl)
        layout.addWidget(editor)
        return field

    form.addWidget(_field("用户名", username_edit))
    form.addWidget(_field("密码", password_edit))

    register_link = QLabel(
        '<a href="https://speclabos.wumiaox.com/register"'
        ' style="color: #5b8def; text-decoration: none;">没有账号？点击注册</a>'
    )
    register_link.setOpenExternalLinks(True)
    register_link.setObjectName("PageHint")
    form.addWidget(register_link)

    form.addWidget(status_label)

    # 按钮
    actions = QHBoxLayout()
    actions.addStretch(1)
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("Secondary")
    cancel_btn.clicked.connect(dialog.reject)
    actions.addWidget(cancel_btn)
    actions.addWidget(login_btn)
    form.addLayout(actions)

    root.addWidget(card)
    username_edit.setFocus()
    password_edit.returnPressed.connect(login_btn.click)

    # ---- 登录逻辑 ----
    auth_result: dict | None = None

    def _set_busy(busy: bool) -> None:
        """切换登录中状态。"""
        username_edit.setEnabled(not busy)
        password_edit.setEnabled(not busy)
        login_btn.setEnabled(not busy)
        login_btn.setText("登录中..." if busy else "登录")
        status_label.setText("正在连接 SpecLabOS 统一门户..." if busy else "")

    def _do_login() -> None:
        """执行登录请求。"""
        nonlocal auth_result
        username = username_edit.text().strip()
        password = password_edit.text()
        if not username:
            QMessageBox.warning(dialog, "无法登录", "请输入用户名。")
            username_edit.setFocus()
            return
        if not password:
            QMessageBox.warning(dialog, "无法登录", "请输入密码。")
            password_edit.setFocus()
            return

        _set_busy(True)
        try:
            base_url = (settings.speclabos_base_url or "").rstrip("/")
            url = f"{base_url}/api/v1/auth/login"
            resp = _http_post_json(
                url,
                {"username": username, "password": password},
                timeout=settings.speclabos_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            _set_busy(False)
            QMessageBox.critical(dialog, "登录失败", str(exc))
            return

        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict):
            _set_busy(False)
            QMessageBox.critical(dialog, "登录失败", "登录响应格式不合法。")
            return
        token = str(data.get("token") or "").strip()
        user_payload = data.get("user")
        if not token or not isinstance(user_payload, dict):
            _set_busy(False)
            QMessageBox.critical(dialog, "登录失败", "登录响应缺少 token 或用户信息。")
            return
        try:
            _register_smartaccess_node(settings, token)
        except Exception as exc:  # noqa: BLE001
            _set_busy(False)
            QMessageBox.critical(dialog, "执行端 ID 冲突", str(exc))
            return

        auth_result = {
            "token": token,
            "username": str(user_payload.get("username") or username),
            "role": str(user_payload.get("role") or ""),
            "organization": str(user_payload.get("organization") or ""),
        }
        dialog.accept()

    login_btn.clicked.connect(_do_login)
    username_edit.returnPressed.connect(password_edit.setFocus)

    if dialog.exec() != QDialog.DialogCode.Accepted or auth_result is None:
        return False

    settings.speclabos_api_key = auth_result["token"]
    settings.speclabos_username = auth_result["username"]
    settings.speclabos_user_role = auth_result["role"]
    settings.speclabos_user_organization = auth_result["organization"]
    settings.platform_provider = "real"
    get_logger().info("用户 %s 登录成功", auth_result["username"])
    return True


def run_app(settings: AppSettings, facade: object | None = None) -> int:
    """启动 Qt 桌面应用。

    Args:
        settings: 应用配置。
        facade: 可选运行时门面。

    Returns:
        Qt 应用退出码。
    """

    logger = get_logger()
    app = QApplication.instance() or QApplication(sys.argv)
    _set_windows_app_id()
    app.setApplicationDisplayName("SmartAccess")
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    from smartaccess.desktop.shell.theme import apply_theme
    apply_theme(app)

    from smartaccess.desktop.shell.main_window import MainWindow
    window = MainWindow(settings, facade=facade)
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    logger.info("桌面主窗口已显示")
    return app.exec()
