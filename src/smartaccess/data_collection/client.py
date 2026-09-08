"""SmartDataHub 数据入库 HTTP 客户端。"""

from __future__ import annotations

import json
from typing import Any

import requests

from .config import ServerConfig
from .models import UploadQueueItem


class DataHubClient:
    """将本地采集文件上传到 SmartDataHub 中心服务。"""

    def __init__(self, config: ServerConfig) -> None:
        """初始化中心服务客户端。

        Args:
            config: 中心服务连接配置。
        """

        self._config = config
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {config.api_token}"})

    def upload_file(self, item: UploadQueueItem) -> dict[str, Any]:
        """上传单个队列文件，并返回中心服务响应。

        Args:
            item: 待上传文件队列条目。

        Returns:
            中心服务返回的 JSON 数据。
        """

        endpoint = f"{self._config.base_url}/api/data/ingest/files"
        with item.file_path.open("rb") as file_object:
            response = self._session.post(
                endpoint,
                data={"metadata": json.dumps(self._build_metadata(item), ensure_ascii=False)},
                files={"file": (item.filename, file_object, item.content_type)},
                timeout=self._config.timeout_seconds,
            )
        response.raise_for_status()
        return response.json() if response.content else {}

    @staticmethod
    def _build_metadata(item: UploadQueueItem) -> dict[str, Any]:
        """构建与 SmartDataHub 兼容的上传元数据。

        Args:
            item: 待上传文件队列条目。

        Returns:
            请求中提交的文件元数据。
        """

        return {
            "collector_id": item.collector_id,
            "device_id": item.device_id,
            "watcher_name": item.watcher_name,
            "watcher_type": item.watcher_type,
            "source_type": "collector",
            "data_type": item.data_type,
            "asset_kind": item.asset_kind,
            "asset_group_id": item.asset_group_id,
            "root_name": item.root_name,
            "relative_path": item.relative_path,
            "filename": item.filename,
            "content_type": item.content_type,
            "file_size": item.file_size,
            "file_hash": item.file_hash,
            "created_at": item.created_at.isoformat(),
            "metadata": item.metadata,
        }
