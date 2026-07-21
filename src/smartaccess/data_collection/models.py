"""数据采集上传队列领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileAssetRecord:
    """写入本地上传队列的文件资产记录。"""

    collector_id: str
    device_id: str
    watcher_name: str
    watcher_type: str
    data_type: str
    asset_kind: str
    asset_group_id: str
    root_name: str
    relative_path: str
    file_path: Path
    filename: str
    content_type: str
    file_size: int
    file_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class UploadQueueItem:
    """本地上传队列的待消费条目。"""

    item_id: int
    collector_id: str
    device_id: str
    watcher_name: str
    watcher_type: str
    data_type: str
    asset_kind: str
    asset_group_id: str
    root_name: str
    relative_path: str
    file_path: Path
    filename: str
    content_type: str
    file_size: int
    file_hash: str
    metadata: dict[str, Any]
    attempt_count: int
    created_at: datetime
