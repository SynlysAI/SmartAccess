"""数据采集本地 SQLite 可靠上传队列。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import FileAssetRecord, TerminalFailureItem, UploadQueueItem


class SQLiteUploadQueue:
    """维护待上传文件资产的本地可靠队列。"""

    def __init__(self, sqlite_path: Path) -> None:
        """初始化 SQLite 上传队列。

        Args:
            sqlite_path: SQLite 数据库文件路径。
        """

        self._sqlite_path = sqlite_path
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def enqueue_file(self, record: FileAssetRecord, force_pending: bool = False) -> int:
        """将文件资产写入待上传队列。

        Args:
            record: 文件资产记录。
            force_pending: 重复记录存在时是否重新置为待上传。

        Returns:
            新建或已存在的队列条目 ID。
        """

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT item_id FROM upload_queue
                WHERE file_path = ? AND file_hash = ?
                """,
                (str(record.file_path), record.file_hash),
            ).fetchone()
            if existing_row is not None:
                item_id = int(existing_row["item_id"])
                if force_pending:
                    connection.execute(
                        """
                        UPDATE upload_queue
                        SET status = 'pending', attempt_count = 0, last_error = NULL,
                            updated_at = ?
                        WHERE item_id = ?
                        """,
                        (_utc_now_text(), item_id),
                    )
                return item_id

            cursor = connection.execute(
                """
                INSERT INTO upload_queue (
                    collector_id, device_id, watcher_name, watcher_type, data_type,
                    asset_kind, asset_group_id, root_name, relative_path, file_path,
                    filename, content_type, file_size, file_hash, metadata_json,
                    status, attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'pending', 0, ?, ?)
                """,
                (
                    record.collector_id,
                    record.device_id,
                    record.watcher_name,
                    record.watcher_type,
                    record.data_type,
                    record.asset_kind,
                    record.asset_group_id,
                    record.root_name,
                    record.relative_path,
                    str(record.file_path),
                    record.filename,
                    record.content_type,
                    record.file_size,
                    record.file_hash,
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at.isoformat(),
                    _utc_now_text(),
                ),
            )
            return int(cursor.lastrowid)

    def list_pending(self, limit: int = 20) -> list[UploadQueueItem]:
        """读取待上传和重试中的队列条目。

        Args:
            limit: 本次最多读取的条目数量。

        Returns:
            待上传条目列表。
        """

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM upload_queue
                WHERE status IN ('pending', 'failed')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def mark_uploaded(self, item_id: int) -> None:
        """标记指定队列条目已上传成功。

        Args:
            item_id: 队列条目 ID。
        """

        self._update_item(item_id, "uploaded", None, increment_attempt=False)

    def mark_failed(
        self,
        item_id: int,
        error_message: str,
        max_retry_count: int,
    ) -> None:
        """记录上传失败并在达到上限后终止自动重试。

        Args:
            item_id: 队列条目 ID。
            error_message: 失败原因。
            max_retry_count: 单个条目允许的最大上传尝试次数。
        """

        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM upload_queue WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return
            attempt_count = int(row["attempt_count"]) + 1
            status = "exhausted" if attempt_count >= max_retry_count else "failed"
            connection.execute(
                """
                UPDATE upload_queue
                SET status = ?, attempt_count = ?, last_error = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (status, attempt_count, error_message[:2000], _utc_now_text(), item_id),
            )

    def list_terminal_failures(self, limit: int = 100) -> list[TerminalFailureItem]:
        """查询已经达到最大重试次数的终止失败条目。

        Args:
            limit: 最多返回的失败条目数量。

        Returns:
            终止失败条目列表，按最近更新时间倒序排列。
        """

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT item_id, filename, file_path, watcher_name, attempt_count, last_error
                FROM upload_queue
                WHERE status = 'exhausted'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            TerminalFailureItem(
                item_id=int(row["item_id"]),
                filename=str(row["filename"]),
                file_path=Path(row["file_path"]),
                watcher_name=str(row["watcher_name"]),
                attempt_count=int(row["attempt_count"]),
                last_error=str(row["last_error"] or "未知错误"),
            )
            for row in rows
        ]

    def retry_terminal_failure(self, item_id: int) -> bool:
        """将终止失败条目重置为待上传状态。

        Args:
            item_id: 终止失败队列条目 ID。

        Returns:
            条目成功重新入队时返回 True。
        """

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE upload_queue
                SET status = 'pending', attempt_count = 0, last_error = NULL,
                    updated_at = ?
                WHERE item_id = ? AND status = 'exhausted'
                """,
                (_utc_now_text(), item_id),
            )
        return cursor.rowcount > 0

    def count_by_status(self) -> dict[str, int]:
        """统计上传队列各状态的数量。

        Returns:
            状态名称到数量的映射。
        """

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM upload_queue GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    def _update_item(
        self,
        item_id: int,
        status: str,
        error_message: str | None,
        *,
        increment_attempt: bool,
    ) -> None:
        """更新队列条目的上传状态。

        Args:
            item_id: 队列条目 ID。
            status: 新状态。
            error_message: 可选失败信息。
            increment_attempt: 是否增加失败重试次数。
        """

        attempt_sql = "attempt_count = attempt_count + 1," if increment_attempt else ""
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE upload_queue
                SET status = ?, {attempt_sql} last_error = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (status, error_message, _utc_now_text(), item_id),
            )

    def _initialize_schema(self) -> None:
        """初始化上传队列表结构和索引。"""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_queue (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collector_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    watcher_name TEXT NOT NULL,
                    watcher_type TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    asset_kind TEXT NOT NULL,
                    asset_group_id TEXT NOT NULL,
                    root_name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_upload_queue_file_hash
                ON upload_queue(file_path, file_hash)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_upload_queue_status
                ON upload_queue(status, created_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """创建一个可用于当前操作的 SQLite 连接。

        Returns:
            配置好行工厂的 SQLite 连接。
        """

        connection = sqlite3.connect(self._sqlite_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection


def _row_to_item(row: sqlite3.Row) -> UploadQueueItem:
    """将 SQLite 查询结果转换为队列条目。

    Args:
        row: SQLite 查询结果行。

    Returns:
        上传队列条目。
    """

    metadata: dict[str, Any] = json.loads(row["metadata_json"] or "{}")
    return UploadQueueItem(
        item_id=int(row["item_id"]),
        collector_id=str(row["collector_id"]),
        device_id=str(row["device_id"]),
        watcher_name=str(row["watcher_name"]),
        watcher_type=str(row["watcher_type"]),
        data_type=str(row["data_type"]),
        asset_kind=str(row["asset_kind"]),
        asset_group_id=str(row["asset_group_id"]),
        root_name=str(row["root_name"]),
        relative_path=str(row["relative_path"]),
        file_path=Path(row["file_path"]),
        filename=str(row["filename"]),
        content_type=str(row["content_type"]),
        file_size=int(row["file_size"]),
        file_hash=str(row["file_hash"]),
        metadata=metadata,
        attempt_count=int(row["attempt_count"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _utc_now_text() -> str:
    """获取当前 UTC 时间的 ISO 文本。"""

    return datetime.now(timezone.utc).isoformat()
