"""远程任务运行上下文共享。"""

from __future__ import annotations

import threading


class ActiveRunContext:
    """记录当前执行端正在运行的 SpecLabOS 平台远程任务。

    数据采集监听器在文件事件到达时刻读取该上下文，把正在执行的
    平台任务 run_id 标注到采集记录上，实现任务与数据文件的源头绑定。
    """

    def __init__(self) -> None:
        """初始化空闲的运行上下文。"""

        self._lock = threading.Lock()
        self._runs: dict[str, int] = {}
        self._sequence = 0

    def begin(self, run_id: str) -> None:
        """登记一个开始执行的远程任务。

        Args:
            run_id: SpecLabOS 平台运行 ID。
        """

        if not run_id:
            return
        with self._lock:
            self._sequence += 1
            self._runs[run_id] = self._sequence

    def end(self, run_id: str) -> None:
        """移除已结束的远程任务。

        Args:
            run_id: SpecLabOS 平台运行 ID。
        """

        with self._lock:
            self._runs.pop(run_id, None)

    def current(self) -> str:
        """读取当前正在执行的任务 ID。

        Returns:
            最近开始且尚未结束的平台任务 ID；无任务执行时返回空字符串。
        """

        with self._lock:
            if not self._runs:
                return ""
            return max(self._runs.items(), key=lambda item: item[1])[0]

    def clear(self) -> None:
        """清空全部运行上下文。"""

        with self._lock:
            self._runs.clear()
            self._sequence = 0


ACTIVE_RUN_CONTEXT = ActiveRunContext()
