"""后台上传工作器。"""

from __future__ import annotations

import logging
import threading

from .client import DataHubClient
from .queue import SQLiteUploadQueue


class UploadWorker:
    """循环消费本地队列并上传到中心服务。"""

    def __init__(
        self,
        queue: SQLiteUploadQueue,
        client: DataHubClient,
        retry_interval_seconds: int,
        max_retry_count: int,
    ) -> None:
        """初始化后台上传工作器。

        Args:
            queue: 本地可靠上传队列。
            client: SmartDataHub HTTP 客户端。
            retry_interval_seconds: 队列为空或失败重试的等待秒数。
            max_retry_count: 单个文件允许的最大上传尝试次数。
        """

        self._queue = queue
        self._client = client
        self._retry_interval_seconds = retry_interval_seconds
        self._max_retry_count = max_retry_count
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="smartaccess-data-uploader",
        )
        self._started = False
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        """启动后台上传线程。"""

        if self._started:
            return
        self._thread.start()
        self._started = True
        self._logger.info("数据采集上传工作器已启动")

    def stop(self) -> None:
        """停止后台上传线程。"""

        self._stop_event.set()
        if self._started and self._thread.is_alive():
            self._thread.join(timeout=10)

    def _run(self) -> None:
        """执行上传消费循环。"""

        while not self._stop_event.is_set():
            items = self._queue.list_pending(limit=10)
            if not items:
                self._stop_event.wait(self._retry_interval_seconds)
                continue
            for item in items:
                if self._stop_event.is_set():
                    break
                if not item.file_path.is_file():
                    self._queue.mark_failed(
                        item.item_id,
                        f"文件不存在: {item.file_path}",
                        self._max_retry_count,
                    )
                    continue
                try:
                    self._client.upload_file(item)
                    self._queue.mark_uploaded(item.item_id)
                    self._logger.info("数据采集文件上传成功: %s", item.file_path)
                except Exception as exc:  # noqa: BLE001
                    self._queue.mark_failed(
                        item.item_id,
                        str(exc),
                        self._max_retry_count,
                    )
                    self._logger.warning(
                        "数据采集文件上传失败 item_id=%s error=%s",
                        item.item_id,
                        exc,
                    )
                    self._stop_event.wait(min(self._retry_interval_seconds, 5))
