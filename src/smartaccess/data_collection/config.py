"""数据采集配置的加载、保存和校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DATA_TYPE_OPTIONS: dict[str, str] = {
    "device_log": "日志类",
    "sample_record": "样品类",
    "report": "报告类",
    "result_data": "数据结果类",
    "other": "其它",
}
LEGACY_DATA_TYPE_ALIASES = {"raw_file": "other"}


@dataclass(frozen=True)
class CollectorIdentity:
    """采集器身份信息。"""

    collector_id: str
    device_id: str
    site: str = ""


@dataclass(frozen=True)
class ServerConfig:
    """SmartDataHub 中心服务连接配置。"""

    base_url: str
    api_token: str
    timeout_seconds: int = 30


@dataclass(frozen=True)
class QueueConfig:
    """本地可靠上传队列配置。"""

    sqlite_path: Path
    retry_interval_seconds: int = 30
    max_retry_count: int = 3


@dataclass(frozen=True)
class WatcherConfig:
    """单个本地数据监听器配置。"""

    name: str
    type: str
    path: Path
    patterns: list[str] = field(default_factory=lambda: ["*"])
    recursive: bool = True
    data_type: str = "other"
    settle_seconds: int = 5
    watch_updates: bool = False
    update_debounce_seconds: int | None = None


@dataclass(frozen=True)
class CollectionConfig:
    """数据采集模块完整配置。"""

    collector: CollectorIdentity
    server: ServerConfig
    queue: QueueConfig
    watchers: list[WatcherConfig]


def default_config(workspace_dir: Path, device_id: str = "") -> CollectionConfig:
    """构建工作区的数据采集默认配置。

    Args:
        workspace_dir: SmartAccess 工作区目录。
        device_id: 当前设备 ID。

    Returns:
        可供页面编辑的默认采集配置。
    """

    data_dir = workspace_dir / "data_collection"
    normalized_device_id = device_id.strip() or "smartaccess_device"
    return CollectionConfig(
        collector=CollectorIdentity(
            collector_id=f"{normalized_device_id}_collector",
            device_id=normalized_device_id,
        ),
        server=ServerConfig(base_url="http://127.0.0.1:8000", api_token=""),
        queue=QueueConfig(sqlite_path=data_dir / "collector_queue.db"),
        watchers=[],
    )


def load_config(config_path: Path) -> CollectionConfig:
    """从兼容 SmartDataHub 的 YAML 文件加载采集配置。

    Args:
        config_path: 配置文件路径。

    Returns:
        解析后的数据采集配置。
    """

    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file) or {}
    return _parse_config(raw_config, config_path.parent)


def save_config(config: CollectionConfig, config_path: Path) -> None:
    """保存数据采集配置为兼容 SmartDataHub 的 YAML 文件。

    Args:
        config: 待保存的数据采集配置。
        config_path: 目标配置文件路径。
    """

    validate_config(config, validate_paths=False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_path = _display_path(config.queue.sqlite_path, config_path.parent)
    raw_config = {
        "collector": {
            "collector_id": config.collector.collector_id,
            "device_id": config.collector.device_id,
            "site": config.collector.site,
        },
        "server": {
            "base_url": config.server.base_url,
            "api_token": config.server.api_token,
            "timeout_seconds": config.server.timeout_seconds,
        },
        "queue": {
            "sqlite_path": sqlite_path,
            "retry_interval_seconds": config.queue.retry_interval_seconds,
            "max_retry_count": config.queue.max_retry_count,
        },
        "watchers": [
            {
                "name": watcher.name,
                "type": watcher.type,
                "path": _display_path(watcher.path, config_path.parent),
                "patterns": watcher.patterns,
                "recursive": watcher.recursive,
                "data_type": watcher.data_type,
                "settle_seconds": watcher.settle_seconds,
                "watch_updates": watcher.watch_updates,
                "update_debounce_seconds": watcher.update_debounce_seconds,
            }
            for watcher in config.watchers
        ],
    }
    config_path.write_text(
        yaml.safe_dump(raw_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def validate_config(config: CollectionConfig, validate_paths: bool = True) -> None:
    """校验采集配置是否可启动。

    Args:
        config: 待校验的采集配置。
        validate_paths: 是否同时校验监听目录存在。

    Raises:
        ValueError: 配置内容不完整或不合法。
    """

    _require_text(config.collector.collector_id, "采集器 ID")
    _require_text(config.collector.device_id, "设备 ID")
    base_url = _require_text(config.server.base_url, "中心服务地址")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("中心服务地址必须以 http:// 或 https:// 开头")
    _require_text(config.server.api_token, "API Token")
    if config.server.timeout_seconds <= 0:
        raise ValueError("请求超时必须大于 0")
    if config.queue.retry_interval_seconds <= 0:
        raise ValueError("重试间隔必须大于 0")
    if config.queue.max_retry_count <= 0:
        raise ValueError("最大重试次数必须大于 0")
    if not config.watchers:
        raise ValueError("请至少添加一个监听器")

    names: set[str] = set()
    for watcher in config.watchers:
        _require_text(watcher.name, "监听器名称")
        if watcher.name in names:
            raise ValueError(f"监听器名称重复: {watcher.name}")
        names.add(watcher.name)
        if watcher.type not in {"file", "directory"}:
            raise ValueError(f"监听器 {watcher.name} 的类型只能是 file 或 directory")
        if not watcher.patterns:
            raise ValueError(f"监听器 {watcher.name} 至少需要一个匹配模式")
        if watcher.data_type not in DATA_TYPE_OPTIONS:
            supported_types = ", ".join(DATA_TYPE_OPTIONS)
            raise ValueError(
                f"监听器 {watcher.name} 的数据类型必须是以下之一: {supported_types}"
            )
        if watcher.settle_seconds < 0:
            raise ValueError(f"监听器 {watcher.name} 的稳定等待时间不能小于 0")
        if (
            watcher.update_debounce_seconds is not None
            and watcher.update_debounce_seconds < 0
        ):
            raise ValueError(f"监听器 {watcher.name} 的更新防抖时间不能小于 0")
        if validate_paths and not watcher.path.is_dir():
            raise ValueError(f"监听目录不存在: {watcher.path}")


def _parse_config(raw_config: dict[str, Any], base_dir: Path) -> CollectionConfig:
    """将 YAML 原始字典转换为强类型采集配置。

    Args:
        raw_config: YAML 解析后的配置字典。
        base_dir: 配置文件所在目录。

    Returns:
        数据采集配置对象。
    """

    collector_raw = _require_mapping(raw_config, "collector")
    server_raw = _require_mapping(raw_config, "server")
    queue_raw = _require_mapping(raw_config, "queue")
    watcher_raw_list = raw_config.get("watchers") or []
    if not isinstance(watcher_raw_list, list):
        raise ValueError("配置项 watchers 必须是列表")

    watchers = [
        _parse_watcher(raw_watcher, base_dir)
        for raw_watcher in watcher_raw_list
        if isinstance(raw_watcher, dict)
    ]
    if len(watchers) != len(watcher_raw_list):
        raise ValueError("配置项 watchers 中存在无效项")
    return CollectionConfig(
        collector=CollectorIdentity(
            collector_id=_require_text(
                collector_raw.get("collector_id"), "collector.collector_id"
            ),
            device_id=_require_text(
                collector_raw.get("device_id"), "collector.device_id"
            ),
            site=str(collector_raw.get("site") or ""),
        ),
        server=ServerConfig(
            base_url=_require_text(server_raw.get("base_url"), "server.base_url").rstrip(
                "/"
            ),
            api_token=_require_text(server_raw.get("api_token"), "server.api_token"),
            timeout_seconds=int(server_raw.get("timeout_seconds", 30)),
        ),
        queue=QueueConfig(
            sqlite_path=_resolve_path(
                queue_raw.get("sqlite_path", "./collector_queue.db"), base_dir
            ),
            retry_interval_seconds=int(queue_raw.get("retry_interval_seconds", 30)),
            max_retry_count=int(queue_raw.get("max_retry_count", 3)),
        ),
        watchers=watchers,
    )


def _parse_watcher(raw_watcher: dict[str, Any], base_dir: Path) -> WatcherConfig:
    """解析单个监听器 YAML 配置。

    Args:
        raw_watcher: 单个监听器原始配置。
        base_dir: 配置文件所在目录。

    Returns:
        监听器配置对象。
    """

    raw_patterns = raw_watcher.get("patterns") or ["*"]
    if not isinstance(raw_patterns, list):
        raise ValueError("watchers.patterns 必须是列表")
    debounce = raw_watcher.get("update_debounce_seconds")
    return WatcherConfig(
        name=_require_text(raw_watcher.get("name"), "watchers.name"),
        type=_require_text(raw_watcher.get("type"), "watchers.type"),
        path=_resolve_path(_require_text(raw_watcher.get("path"), "watchers.path"), base_dir),
        patterns=[str(pattern).strip() for pattern in raw_patterns if str(pattern).strip()],
        recursive=bool(raw_watcher.get("recursive", True)),
        data_type=_normalize_data_type(raw_watcher.get("data_type")),
        settle_seconds=int(raw_watcher.get("settle_seconds", 5)),
        watch_updates=bool(raw_watcher.get("watch_updates", False)),
        update_debounce_seconds=int(debounce) if debounce is not None else None,
    )


def _normalize_data_type(value: object) -> str:
    """标准化数据类型，并兼容旧配置名称。

    Args:
        value: YAML 中的原始数据类型值。

    Returns:
        平台约定的数据类型值。
    """

    data_type = str(value or "other").strip()
    return LEGACY_DATA_TYPE_ALIASES.get(data_type, data_type)


def _require_mapping(raw_config: dict[str, Any], key: str) -> dict[str, Any]:
    """读取必填字典配置段。

    Args:
        raw_config: 完整原始配置。
        key: 配置段名称。

    Returns:
        对应的字典配置。
    """

    value = raw_config.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"配置项 {key} 必须是对象")
    return value


def _require_text(value: object, name: str) -> str:
    """读取并校验必填文本字段。

    Args:
        value: 原始字段值。
        name: 用于错误提示的字段名。

    Returns:
        清理后的文本值。
    """

    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _resolve_path(value: object, base_dir: Path) -> Path:
    """将配置中的相对路径解析为绝对路径。

    Args:
        value: 原始路径字段。
        base_dir: 相对路径基准目录。

    Returns:
        标准化后的绝对路径。
    """

    path = Path(_require_text(value, "路径")).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _display_path(path: Path, base_dir: Path) -> str:
    """将绝对路径转换为可移植的配置文件路径。

    Args:
        path: 待显示路径。
        base_dir: 配置文件所在目录。

    Returns:
        相对路径优先的文本路径。
    """

    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path)
