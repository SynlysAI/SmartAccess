"""数据采集页面视图模型。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

from smartaccess.data_collection.config import (
    CollectionConfig,
    CollectorIdentity,
    QueueConfig,
    ServerConfig,
    WatcherConfig,
    default_config,
    load_config,
    save_config,
)
from smartaccess.data_collection.controller import (
    CollectionController,
    CollectionRuntimeStatus,
)

from .base import ViewModel


class DataCollectionViewModel(ViewModel):
    """适配数据采集页面与应用内采集控制器。"""

    def __init__(self, facade, parent=None) -> None:
        """初始化数据采集视图模型。

        Args:
            facade: SmartAccess 运行时门面。
            parent: 可选 Qt 父对象。
        """

        super().__init__(facade, parent)
        self._controller = CollectionController()
        self._config_path = self._facade.workspace_dir() / "data_collection" / "collector.yaml"

    def load_configuration(self) -> CollectionConfig:
        """加载工作区采集配置；不存在时返回默认配置。

        Returns:
            可在页面中编辑的数据采集配置。
        """

        config = (
            load_config(self._config_path)
            if self._config_path.is_file()
            else default_config(
                self._facade.workspace_dir(),
                self._facade.settings().device_id,
            )
        )
        return self._apply_environment_settings(config, require_values=False)

    def build_configuration(
        self,
        *,
        collector_id: str,
        site: str,
        timeout_seconds: int,
        retry_interval_seconds: int,
        watchers: Iterable[WatcherConfig],
    ) -> CollectionConfig:
        """根据页面可编辑字段构造采集配置。

        设备 ID、中心服务地址和数据采集密钥由 `.env` 统一提供，
        不允许通过桌面页面覆盖。

        Args:
            collector_id: 采集器标识。
            site: 采集站点名称。
            timeout_seconds: 单文件上传请求超时秒数。
            retry_interval_seconds: 上传失败重试间隔秒数。
            watchers: 页面配置的监听器列表。

        Returns:
            已应用环境变量的完整采集配置。
        """

        config = CollectionConfig(
            collector=CollectorIdentity(
                collector_id=collector_id,
                device_id="",
                site=site,
            ),
            server=ServerConfig(base_url="", api_token="", timeout_seconds=timeout_seconds),
            queue=QueueConfig(
                sqlite_path=(
                    self._facade.workspace_dir()
                    / "data_collection"
                    / "collector_queue.db"
                ),
                retry_interval_seconds=retry_interval_seconds,
            ),
            watchers=list(watchers),
        )
        return self._apply_environment_settings(config, require_values=True)

    def save_configuration(self, config: CollectionConfig) -> Path:
        """保存页面填写的数据采集配置。

        Args:
            config: 待保存的数据采集配置。

        Returns:
            已保存的配置文件路径。
        """

        effective_config = self._apply_environment_settings(config, require_values=True)
        save_config(effective_config, self._config_path)
        return self._config_path

    def start(
        self,
        config: CollectionConfig,
        *,
        upload_existing: bool,
        force_upload_existing: bool,
    ) -> None:
        """保存配置并启动应用内采集器。

        Args:
            config: 页面填写的数据采集配置。
            upload_existing: 是否扫描现有数据。
            force_upload_existing: 是否强制重传现有数据。
        """

        effective_config = self._apply_environment_settings(config, require_values=True)
        save_config(effective_config, self._config_path)
        self._controller.start(
            effective_config,
            upload_existing=upload_existing,
            force_upload_existing=force_upload_existing,
        )
        self.changed.emit()

    def stop(self) -> None:
        """停止正在运行的数据采集器。"""

        self._controller.stop()
        self.changed.emit()

    def status(self) -> CollectionRuntimeStatus:
        """返回数据采集器的实时状态。

        Returns:
            数据采集运行状态摘要。
        """

        return self._controller.status()

    def is_running(self) -> bool:
        """返回数据采集器是否处于启动或运行状态。

        Returns:
            运行中时返回 True。
        """

        return self._controller.is_running

    def _apply_environment_settings(
        self,
        config: CollectionConfig,
        *,
        require_values: bool,
    ) -> CollectionConfig:
        """使用应用环境变量覆盖采集器运行连接配置。

        Args:
            config: 页面或配置文件提供的基础采集配置。
            require_values: 是否要求 `.env` 中的运行配置均已填写。

        Returns:
            设备与中心服务信息已统一为环境变量值的配置。

        Raises:
            ValueError: 启动或保存时缺少必填环境变量。
        """

        settings = self._facade.settings()
        device_id = settings.device_id.strip()
        base_url = (settings.speclabos_base_url or "").strip().rstrip("/")
        datahub_key = (settings.speclabos_datahub_key or "").strip()
        if require_values and not device_id:
            raise ValueError("请先在 .env 中配置 SMARTACCESS_DEVICE_ID")
        if require_values and not base_url:
            raise ValueError("请先在 .env 中配置 SPECLABOS_BASE_URL")
        if require_values and not datahub_key:
            raise ValueError("请先在 .env 中配置 SPECLABOS_DATAHUB_KEY")
        return replace(
            config,
            collector=replace(config.collector, device_id=device_id),
            server=replace(
                config.server,
                base_url=base_url,
                api_token=datahub_key,
            ),
        )
