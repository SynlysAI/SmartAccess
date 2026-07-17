"""SmartAccess 执行端心跳上报器。

周期向 SpecLabOS 平台上报心跳,让平台知道本节点在线。
失败时静默重试,不影响本地运行;仅在配置了 SpecLabOS 平台地址时启动。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from smartaccess.runtime.application.ports import PlatformClient, PlatformOffline
from smartaccess.shared.config.settings import AppSettings

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30


def build_device_info(settings: AppSettings) -> dict[str, Any]:
    """从应用配置构造上报给平台的设备元信息。

    Args:
        settings: 应用配置。

    Returns:
        上报给平台的设备信息字典。
    """
    return {
        "workspace_dir": str(settings.workspace_dir),
        "automation_provider": settings.automation_provider,
        "vision_provider": settings.vision_provider,
        "ocr_mode": settings.ocr_mode,
        "process_executor_provider": settings.process_executor_provider,
        "rabbitmq_enabled": settings.rabbitmq_enabled,
        "edge_api_host": settings.edge_api_host,
        "edge_api_port": settings.edge_api_port,
        "speclabos_base_url": settings.speclabos_base_url or "",
    }


class HeartbeatReporter:
    """周期上报执行端心跳到 SpecLabOS 平台。

    仅当 ``node_id`` 非空(即配置了 ``SMARTACCESS_DEVICE_ID``)且平台客户端
    非 Stub 时才会真正上报;否则跳过,避免在未接入平台的本地模式下产生噪音。
    """

    def __init__(
        self,
        *,
        platform: PlatformClient,
        settings: AppSettings,
        interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        """初始化心跳上报器。

        Args:
            platform: 平台客户端。
            settings: 应用配置。
            interval_seconds: 上报周期秒数。
        """
        self._platform = platform
        self._node_id = settings.device_id or ""
        self._device_info = build_device_info(settings)
        self._interval = max(5, int(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台心跳线程。"""
        if not self._node_id:
            logger.info("未配置 SMARTACCESS_DEVICE_ID,跳过心跳上报")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="smartaccess-heartbeat",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "SmartAccess 心跳上报已启动: node_id=%s, 周期=%ds",
            self._node_id,
            self._interval,
        )

    def stop(self) -> None:
        """停止后台心跳线程。"""
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def beat_once(self) -> bool:
        """立即上报一次心跳。

        Returns:
            平台接收成功返回 True,否则 False。
        """
        if not self._node_id:
            return False
        payload = {
            "node_id": self._node_id,
            "device_info": self._device_info,
            "heartbeat_interval_seconds": self._interval,
        }
        try:
            ok = bool(self._platform.report_heartbeat(payload))
        except PlatformOffline as exc:
            logger.debug("心跳上报失败,平台离线: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 - 心跳失败不能影响主流程
            logger.debug("心跳上报异常: %s", exc)
            return False
        if ok:
            logger.debug("心跳上报成功: node_id=%s", self._node_id)
        return ok

    def _loop(self) -> None:
        """周期上报心跳,启动时立即上报一次。"""
        self.beat_once()
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break
            self.beat_once()


def start_heartbeat_reporter(
    settings: AppSettings,
    *,
    platform: PlatformClient | None = None,
    facade=None,
    interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> HeartbeatReporter | None:
    """启动 SmartAccess 心跳上报器。

    优先使用传入的 ``platform``;否则从 ``facade`` 提取;都没有则跳过。

    Args:
        settings: 应用配置。
        platform: 可选平台客户端;为空时从 facade 提取。
        facade: 可选运行时门面,用于提取 platform。
        interval_seconds: 上报周期秒数。

    Returns:
        已启动的心跳上报器;未启动时返回 None。
    """
    if platform is None and facade is not None:
        try:
            platform = facade.providers()["platform"]
        except Exception:  # noqa: BLE001
            platform = None
    if platform is None:
        logger.info("未提供平台客户端,跳过心跳上报")
        return None

    reporter = HeartbeatReporter(
        platform=platform,
        settings=settings,
        interval_seconds=interval_seconds,
    )
    reporter.start()
    return reporter
