"""数据采集与远程任务绑定测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from smartaccess.data_collection.client import DataHubClient
from smartaccess.data_collection.config import CollectorIdentity, WatcherConfig
from smartaccess.data_collection.models import UploadQueueItem
from smartaccess.data_collection.queue import SQLiteUploadQueue
from smartaccess.data_collection.run_context import ACTIVE_RUN_CONTEXT, ActiveRunContext
from smartaccess.data_collection.watcher import CollectorFileWatcher


def _watcher(tmp_path: Path, watch_dir: Path) -> CollectorFileWatcher:
    """构造测试用文件监听器。

    Args:
        tmp_path: 测试临时目录，用于 SQLite 队列。
        watch_dir: 监听目录。

    Returns:
        未启动的监听器实例。
    """

    config = WatcherConfig(
        name="results",
        type="file",
        path=watch_dir,
        patterns=["*.csv"],
        data_type="result_data",
        settle_seconds=0,
    )
    queue = SQLiteUploadQueue(tmp_path / "queue.sqlite3")
    return CollectorFileWatcher(
        CollectorIdentity(collector_id="pc-collector", device_id="pc-workstation"),
        config,
        queue,
    )


def test_active_run_context_tracks_latest_run() -> None:
    """验证运行上下文登记、清理与并发任务取最新。"""

    context = ActiveRunContext()
    assert context.current() == ""

    context.begin("run_1")
    context.begin("run_2")
    assert context.current() == "run_2"

    context.end("run_2")
    assert context.current() == "run_1"

    context.end("run_1")
    assert context.current() == ""


def test_watcher_stamps_active_run_id(tmp_path: Path) -> None:
    """验证任务执行期间监听到的文件会打上任务标记。"""

    watch_dir = tmp_path / "results"
    watch_dir.mkdir()
    watcher = _watcher(tmp_path, watch_dir)
    data_file = watch_dir / "sample.csv"
    data_file.write_text("a,b\n1,2\n", encoding="utf-8")

    ACTIVE_RUN_CONTEXT.clear()
    ACTIVE_RUN_CONTEXT.begin("sa_run_target_001")
    try:
        stamped = watcher._build_record(
            file_path=data_file,
            asset_kind="file",
            asset_group_id=data_file.name,
            root_name=data_file.name,
            relative_path=data_file.name,
            active_run_id=ACTIVE_RUN_CONTEXT.current(),
        )
    finally:
        ACTIVE_RUN_CONTEXT.clear()

    assert stamped.metadata["device_run_id"] == "sa_run_target_001"

    unstamped = watcher._build_record(
        file_path=data_file,
        asset_kind="file",
        asset_group_id=data_file.name,
        root_name=data_file.name,
        relative_path=data_file.name,
        active_run_id="",
    )
    assert "device_run_id" not in unstamped.metadata


def test_upload_metadata_hoists_device_run_id() -> None:
    """验证上传元数据把任务标记提升到顶层。"""

    item = UploadQueueItem(
        item_id=1,
        collector_id="pc-collector",
        device_id="pc-workstation",
        watcher_name="results",
        watcher_type="file",
        data_type="result_data",
        asset_kind="file",
        asset_group_id="sample.csv",
        root_name="sample.csv",
        relative_path="sample.csv",
        file_path=Path("sample.csv"),
        filename="sample.csv",
        content_type="text/csv",
        file_size=8,
        file_hash="hash",
        metadata={"source_path": "x", "device_run_id": "sa_run_target_001"},
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
    )

    metadata = DataHubClient._build_metadata(item)

    assert metadata["device_run_id"] == "sa_run_target_001"
    assert metadata["metadata"]["device_run_id"] == "sa_run_target_001"
