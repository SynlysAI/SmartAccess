"""SmartAccess 桌面单实例守卫。"""

from __future__ import annotations

import weakref

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QWidget

_SERVER_NAME = "smartaccess-desktop-singleton"


class SingleInstanceGuard:
    """保证桌面应用只运行一个实例，二次启动时唤醒已有实例的窗口。

    首个实例通过 QLocalServer 监听命名管道；后续实例启动时先探测该
    管道，命中后发送唤醒请求并把已有窗口带回前台，随后自行退出。
    """

    def __init__(self) -> None:
        self._server: QLocalServer | None = None
        self._target: weakref.ReferenceType[QWidget] | None = None

    def poke_existing(self, timeout_ms: int = 1500) -> bool:
        """探测是否已有实例在运行，并请求其激活窗口。

        Args:
            timeout_ms: 连接既有实例的超时时间（毫秒）。

        Returns:
            已有实例并已发出唤醒请求返回 True；当前是第一个实例返回 False。
        """
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if not socket.waitForConnected(timeout_ms):
            return False
        # 激活由既有实例的 newConnection 信号触发，写入仅作补充标记，
        # 不要求送达确认，避免对端事件循环繁忙时误判为无实例
        socket.write(b"activate")
        socket.flush()
        socket.disconnectFromServer()
        return True

    def start(self) -> bool:
        """开始监听后续实例的唤醒请求。

        Returns:
            监听创建成功返回 True；失败返回 False（调用方可继续运行）。
        """
        QLocalServer.removeServer(_SERVER_NAME)
        server = QLocalServer()
        if not server.listen(_SERVER_NAME):
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def set_target(self, window: QWidget) -> None:
        """设置唤醒时需要带回前台的目标窗口。

        Args:
            window: 应用主窗口。
        """
        self._target = weakref.ref(window)

    def activate(self) -> None:
        """把目标窗口带回前台显示。

        未设置目标窗口（如首个实例还停留在登录框）时，退化为激活
        当前活动窗口；两者都缺省时不做任何操作。
        """
        window = self._target() if self._target is not None else None
        if window is None:
            app = QApplication.instance()
            window = app.activeWindow() if app is not None else None
        if window is None:
            return
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()

    def _on_new_connection(self) -> None:
        """处理二次实例发来的唤醒请求。"""
        server = self._server
        if server is None:
            return
        connection = server.nextPendingConnection()
        if connection is None:
            return
        connection.readyRead.connect(lambda: connection.readAll())
        connection.disconnected.connect(connection.deleteLater)
        self.activate()
