"""数据采集器的应用内生命周期控制器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading

from .config import CollectionConfig, validate_config
from .models import TerminalFailureItem
from .queue import SQLiteUploadQueue


@dataclass(frozen=True)
class CollectionRuntimeStatus:
    """数据采集器当前运行状态摘要。"""

    state: str
    message: str
    started_at: datetime | None
    watcher_states: tuple[tuple[str, str, bool], ...]
    queue_counts: dict[str, int]
    initial_scan_files: int


class CollectionController:
    """在 SmartAccess 进程内启动、停止和监控数据采集器。"""

    def __init__(self) -> None:
        """初始化空闲的数据采集器控制器。"""

        self._lock = threading.RLock()
        self._config: CollectionConfig | None = None
        self._queue: SQLiteUploadQueue | None = None
        self._uploader = None
        self._watchers: list[object] = []
        self._state = "stopped"
        self._message = "未启动"
        self._started_at: datetime | None = None
        self._initial_scan_files = 0

    @property
    def is_running(self) -> bool:
        """返回采集器是否正在运行。"""

        with self._lock:
            return self._state in {"starting", "running"}

    def load_queue(self, config: CollectionConfig) -> None:
        """关联配置对应的本地上传队列以便展示历史状态。

        Args:
            config: 当前数据采集配置。
        """

        with self._lock:
            if self._state in {"starting", "running"}:
                return
            self._queue = SQLiteUploadQueue(config.queue.sqlite_path)

    def start(
        self,
        config: CollectionConfig,
        *,
        upload_existing: bool,
        force_upload_existing: bool,
    ) -> None:
        """启动监听器和上传工作器。

        Args:
            config: 已由页面填写的采集配置。
            upload_existing: 是否先扫描当前已有的数据。
            force_upload_existing: 是否强制重置历史数据的上传状态。

        Raises:
            RuntimeError: 采集器已经运行。
            ValueError: 配置不完整或监听目录不存在。
        """

        with self._lock:
            if self._state in {"starting", "running"}:
                raise RuntimeError("数据采集器已经在运行")
            self._state = "starting"
            self._message = "正在初始化监听器"
            self._config = config
            self._queue = None
            self._uploader = None
            self._watchers = []
            self._initial_scan_files = 0

        try:
            validate_config(config, validate_paths=True)
            from .client import DataHubClient
            from .uploader import UploadWorker
            from .watcher import CollectorFileWatcher

            queue = SQLiteUploadQueue(config.queue.sqlite_path)
            watchers = [
                CollectorFileWatcher(config.collector, watcher_config, queue)
                for watcher_config in config.watchers
            ]
            uploader = UploadWorker(
                queue=queue,
                client=DataHubClient(config.server),
                retry_interval_seconds=config.queue.retry_interval_seconds,
                max_retry_count=config.queue.max_retry_count,
            )
            initial_scan_files = 0
            if upload_existing:
                for watcher in watchers:
                    initial_scan_files += watcher.upload_existing(
                        force_upload=force_upload_existing
                    )
            for watcher in watchers:
                watcher.start()
            uploader.start()
        except Exception as exc:
            self._cleanup(uploader=locals().get("uploader"), watchers=locals().get("watchers", []))
            with self._lock:
                self._state = "error"
                self._message = str(exc)
                self._started_at = None
            raise

        with self._lock:
            self._queue = queue
            self._uploader = uploader
            self._watchers = watchers
            self._state = "running"
            self._message = "正在监听并上传数据"
            self._started_at = datetime.now()
            self._initial_scan_files = initial_scan_files

    def stop(self) -> None:
        """停止监听器和上传工作器。"""

        with self._lock:
            uploader = self._uploader
            watchers = list(self._watchers)
            self._state = "stopping"
            self._message = "正在停止采集器"
        self._cleanup(uploader=uploader, watchers=watchers)
        with self._lock:
            self._uploader = None
            self._watchers = []
            self._state = "stopped"
            self._message = "已停止"
            self._started_at = None

    def status(self) -> CollectionRuntimeStatus:
        """返回当前采集器、监听器和上传队列状态。

        Returns:
            可直接绑定到页面的数据采集运行状态。
        """

        with self._lock:
            queue = self._queue
            watcher_states = tuple(
                (
                    watcher.name,
                    str(watcher.path),
                    bool(watcher.is_running),
                )
                for watcher in self._watchers
            )
            state = self._state
            message = self._message
            started_at = self._started_at
            initial_scan_files = self._initial_scan_files
        queue_counts = queue.count_by_status() if queue is not None else {}
        return CollectionRuntimeStatus(
            state=state,
            message=message,
            started_at=started_at,
            watcher_states=watcher_states,
            queue_counts=queue_counts,
            initial_scan_files=initial_scan_files,
        )

    def list_terminal_failures(self) -> list[TerminalFailureItem]:
        """查询当前上传队列中的终止失败条目。

        Returns:
            已停止自动重试的队列条目列表。
        """

        with self._lock:
            queue = self._queue
        return queue.list_terminal_failures() if queue is not None else []

    def retry_terminal_failure(self, item_id: int) -> bool:
        """将指定终止失败条目重新放入待上传队列。

        Args:
            item_id: 终止失败队列条目 ID。

        Returns:
            成功重新入队时返回 True。
        """

        with self._lock:
            queue = self._queue
        return queue.retry_terminal_failure(item_id) if queue is not None else False

    @staticmethod
    def _cleanup(uploader: object | None, watchers: list[object]) -> None:
        """安全停止已经创建的采集运行对象。

        Args:
            uploader: 可选上传工作器。
            watchers: 已创建的文件监听器列表。
        """

        if uploader is not None:
            uploader.stop()
        for watcher in watchers:
            watcher.stop()
