"""后台任务线程工具。"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal


class BackgroundTask(QThread):
    """在后台线程执行耗时任务，完成后通过信号通知主线程。"""

    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        task: Callable[[], Any],
        parent: QObject | None = None,
    ) -> None:
        """初始化后台任务线程。

        Args:
            task: 耗时任务。
            parent: Qt 父对象，确保线程随父对象销毁。
        """

        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        """执行任务并发送信号。"""

        try:
            result = self._task()
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
