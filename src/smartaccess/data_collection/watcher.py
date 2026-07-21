"""基于 watchdog 的本地文件与目录采集监听器。"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import CollectorIdentity, WatcherConfig
from .models import FileAssetRecord
from .queue import SQLiteUploadQueue


class CollectorFileWatcher:
    """监听本地数据目录，并把稳定的数据资产写入上传队列。"""

    def __init__(
        self,
        identity: CollectorIdentity,
        config: WatcherConfig,
        queue: SQLiteUploadQueue,
    ) -> None:
        """初始化一个数据监听器。

        Args:
            identity: 采集器身份配置。
            config: 监听器配置。
            queue: 本地可靠上传队列。
        """

        self._identity = identity
        self._config = config
        self._queue = queue
        self._observer = Observer()
        self._stop_event = threading.Event()
        self._processing_paths: set[Path] = set()
        self._last_update_at: dict[Path, float] = {}
        self._lock = threading.Lock()
        self._started = False
        self._logger = logging.getLogger(__name__)

    @property
    def name(self) -> str:
        """返回监听器名称。"""

        return self._config.name

    @property
    def path(self) -> Path:
        """返回监听目录路径。"""

        return self._config.path

    @property
    def is_running(self) -> bool:
        """返回监听器是否正在运行。"""

        return self._started and self._observer.is_alive()

    def start(self) -> None:
        """启动文件系统监听。"""

        if self._started:
            return
        if not self._config.path.is_dir():
            raise FileNotFoundError(f"监听目录不存在: {self._config.path}")
        handler = _FileEventHandler(self)
        self._observer.schedule(
            handler,
            str(self._config.path),
            recursive=self._config.recursive,
        )
        self._observer.start()
        self._started = True
        self._logger.info("数据采集监听器已启动 %s: %s", self.name, self.path)

    def stop(self) -> None:
        """停止文件系统监听及后续待处理任务。"""

        self._stop_event.set()
        if self._started:
            self._observer.stop()
            self._observer.join(timeout=10)
        self._started = False

    def upload_existing(self, force_upload: bool = False) -> int:
        """扫描当前监听目录中的已有数据。

        Args:
            force_upload: 是否将重复文件重新置为待上传。

        Returns:
            写入队列的文件数量。
        """

        if not self._config.path.is_dir():
            raise FileNotFoundError(f"监听目录不存在: {self._config.path}")
        if self._config.type == "directory":
            total = 0
            for asset_path in self._config.path.iterdir():
                if asset_path.is_dir() and self._matches(asset_path.name):
                    total += self._enqueue_directory(asset_path, force_upload)
            return total

        file_iterator = (
            self._config.path.rglob("*")
            if self._config.recursive
            else self._config.path.glob("*")
        )
        total = 0
        for file_path in file_iterator:
            if file_path.is_file() and self._matches(file_path.name):
                total += int(self._enqueue_file(file_path, force_upload))
        return total

    def handle_event(self, path: Path, is_directory: bool, is_update: bool) -> None:
        """将文件系统事件转换为异步采集任务。

        Args:
            path: 事件对应路径。
            is_directory: 事件路径是否为目录。
            is_update: 是否由修改事件触发。
        """

        target_path = self._resolve_target(path, is_directory)
        if target_path is None or self._stop_event.is_set():
            return
        if is_update and not self._accept_update(target_path):
            return
        with self._lock:
            if target_path in self._processing_paths:
                return
            self._processing_paths.add(target_path)
        thread = threading.Thread(
            target=self._process_target,
            args=(target_path,),
            daemon=True,
            name=f"smartaccess-data-watch-{self._config.name}",
        )
        thread.start()

    def _process_target(self, target_path: Path) -> None:
        """等待资产稳定后写入上传队列。

        Args:
            target_path: 要采集的文件或目录资产路径。
        """

        try:
            if self._config.type == "directory":
                if self._wait_directory_settled(target_path):
                    self._enqueue_directory(target_path, force_upload=False)
            elif self._wait_file_settled(target_path):
                self._enqueue_file(target_path, force_upload=False)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("采集文件处理失败 path=%s error=%s", target_path, exc)
        finally:
            with self._lock:
                self._processing_paths.discard(target_path)

    def _resolve_target(self, path: Path, is_directory: bool) -> Path | None:
        """根据事件路径定位需要上传的文件或目录资产。

        Args:
            path: 原始文件系统事件路径。
            is_directory: 原始路径是否为目录。

        Returns:
            需要采集的资产路径；不匹配时返回 None。
        """

        try:
            relative_path = path.resolve().relative_to(self._config.path.resolve())
        except ValueError:
            return None
        if not relative_path.parts:
            return None
        if self._config.type == "file":
            if is_directory or not self._matches(path.name):
                return None
            return path
        asset_path = self._config.path / relative_path.parts[0]
        if not asset_path.is_dir() or not self._matches(asset_path.name):
            return None
        return asset_path

    def _enqueue_file(self, file_path: Path, force_upload: bool) -> bool:
        """将单个文件构造成资产记录并写入队列。

        Args:
            file_path: 待入队文件路径。
            force_upload: 是否强制重置重复文件状态。

        Returns:
            文件成功入队时返回 True。
        """

        if not file_path.is_file() or self._stop_event.is_set():
            return False
        relative_path = file_path.relative_to(self._config.path)
        record = self._build_record(
            file_path=file_path,
            asset_kind="file",
            asset_group_id=file_path.name,
            root_name=file_path.name,
            relative_path=str(relative_path).replace("\\", "/"),
        )
        self._queue.enqueue_file(record, force_pending=force_upload)
        return True

    def _enqueue_directory(self, directory_path: Path, force_upload: bool) -> int:
        """将目录资产内的所有文件按原相对路径写入队列。

        Args:
            directory_path: 待采集目录资产路径。
            force_upload: 是否强制重置重复文件状态。

        Returns:
            写入队列的文件数量。
        """

        if not directory_path.is_dir() or self._stop_event.is_set():
            return 0
        total = 0
        for file_path in directory_path.rglob("*"):
            if not file_path.is_file() or self._stop_event.is_set():
                continue
            relative_path = file_path.relative_to(directory_path)
            record = self._build_record(
                file_path=file_path,
                asset_kind="directory",
                asset_group_id=directory_path.name,
                root_name=directory_path.name,
                relative_path=str(relative_path).replace("\\", "/"),
            )
            self._queue.enqueue_file(record, force_pending=force_upload)
            total += 1
        return total

    def _build_record(
        self,
        *,
        file_path: Path,
        asset_kind: str,
        asset_group_id: str,
        root_name: str,
        relative_path: str,
    ) -> FileAssetRecord:
        """构造与 SmartDataHub 兼容的文件资产记录。

        Args:
            file_path: 本地文件路径。
            asset_kind: 资产类型。
            asset_group_id: 资产分组标识。
            root_name: 资产根名称。
            relative_path: 文件在资产内的相对路径。

        Returns:
            可写入上传队列的文件资产记录。
        """

        return FileAssetRecord(
            collector_id=self._identity.collector_id,
            device_id=self._identity.device_id,
            watcher_name=self._config.name,
            watcher_type=self._config.type,
            data_type=self._config.data_type,
            asset_kind=asset_kind,
            asset_group_id=asset_group_id,
            root_name=root_name,
            relative_path=relative_path,
            file_path=file_path,
            filename=file_path.name,
            content_type=mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream",
            file_size=file_path.stat().st_size,
            file_hash=_calculate_sha256(file_path),
            metadata={"source_path": str(file_path)},
        )

    def _matches(self, name: str) -> bool:
        """判断文件或目录名称是否符合监听器模式。

        Args:
            name: 待匹配名称。

        Returns:
            名称匹配任一模式时返回 True。
        """

        return any(Path(name).match(pattern) for pattern in self._config.patterns)

    def _accept_update(self, target_path: Path) -> bool:
        """按配置的防抖时间过滤高频修改事件。

        Args:
            target_path: 本次事件目标路径。

        Returns:
            事件可继续处理时返回 True。
        """

        debounce_seconds = self._config.update_debounce_seconds or 0
        if debounce_seconds <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            previous = self._last_update_at.get(target_path)
            self._last_update_at[target_path] = now
        return previous is None or now - previous >= debounce_seconds

    def _wait_file_settled(self, file_path: Path) -> bool:
        """等待文件尺寸和修改时间在稳定窗口内不再变化。

        Args:
            file_path: 待检测文件路径。

        Returns:
            文件稳定且仍存在时返回 True。
        """

        return self._wait_settled(file_path, is_directory=False)

    def _wait_directory_settled(self, directory_path: Path) -> bool:
        """等待目录内文件快照在稳定窗口内不再变化。

        Args:
            directory_path: 待检测目录路径。

        Returns:
            目录稳定且仍存在时返回 True。
        """

        return self._wait_settled(directory_path, is_directory=True)

    def _wait_settled(self, target_path: Path, is_directory: bool) -> bool:
        """等待指定文件或目录的快照达到稳定状态。

        Args:
            target_path: 待检测路径。
            is_directory: 路径是否为目录。

        Returns:
            目标稳定且未被停止时返回 True。
        """

        stable_seconds = self._config.settle_seconds
        previous_snapshot: object | None = None
        stable_since = time.monotonic()
        while not self._stop_event.is_set():
            if is_directory:
                if not target_path.is_dir():
                    return False
                current_snapshot = tuple(
                    (str(path.relative_to(target_path)), path.stat().st_size, path.stat().st_mtime_ns)
                    for path in target_path.rglob("*")
                    if path.is_file()
                )
            else:
                if not target_path.is_file():
                    return False
                stat_result = target_path.stat()
                current_snapshot = (stat_result.st_size, stat_result.st_mtime_ns)
            if current_snapshot != previous_snapshot:
                previous_snapshot = current_snapshot
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= stable_seconds:
                return True
            self._stop_event.wait(1)
        return False


class _FileEventHandler(FileSystemEventHandler):
    """转发创建、移动和修改事件到采集监听器。"""

    def __init__(self, watcher: CollectorFileWatcher) -> None:
        """初始化文件系统事件处理器。

        Args:
            watcher: 所属数据采集监听器。
        """

        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        """处理文件或目录创建事件。

        Args:
            event: watchdog 文件系统事件。
        """

        self._watcher.handle_event(Path(event.src_path), event.is_directory, False)

    def on_moved(self, event: FileSystemEvent) -> None:
        """处理文件或目录移动进入监听目录的事件。

        Args:
            event: watchdog 文件系统事件。
        """

        destination = getattr(event, "dest_path", None)
        if destination:
            self._watcher.handle_event(Path(destination), event.is_directory, False)

    def on_modified(self, event: FileSystemEvent) -> None:
        """处理允许采集更新内容的修改事件。

        Args:
            event: watchdog 文件系统事件。
        """

        if not self._watcher._config.watch_updates:
            return
        self._watcher.handle_event(Path(event.src_path), event.is_directory, True)


def _calculate_sha256(file_path: Path) -> str:
    """计算文件内容的 SHA256 哈希。

    Args:
        file_path: 待计算的文件路径。

    Returns:
        文件 SHA256 十六进制摘要。
    """

    digest = hashlib.sha256()
    with file_path.open("rb") as file_object:
        while block := file_object.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
