"""锚点配置服务。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from smartaccess.shared.contracts.anchors import (
    AnchorDefinition,
    AnchorsContract,
    ExceptionRule,
    WindowSignature,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.validation import require_valid_device_id
from smartaccess.shared.logging import get_logger


class AnchorService:
    """管理工作区下的锚点配置。"""

    def __init__(self, *, workspace_dir: Path) -> None:
        """初始化锚点服务。

        Args:
            workspace_dir: 工作区目录。
        """

        self._workspace_dir = Path(workspace_dir)
        self._profiles: dict[str, AnchorsContract] = {}
        self._logger = get_logger()
        self.load_all()

    def load_all(self) -> None:
        """加载全部锚点配置。"""

        self._profiles.clear()
        loaded_count = 0
        for path in sorted((self._workspace_dir / "anchors").glob("*/anchors.yaml")):
            try:
                profile = load_yaml_contract(path, AnchorsContract)
            except Exception:  # noqa: BLE001 - 单个坏文件不能阻断启动
                self._logger.exception("锚点配置加载失败: %s", path)
                continue
            self._profiles[profile.profile_id] = profile
            loaded_count += 1
        if loaded_count:
            self._logger.info("已加载 %d 个锚点配置", loaded_count)

    def create_profile(
        self,
        *,
        profile_id: str,
        title_contains: str,
        anchors: list[dict[str, Any]] | None = None,
        views: list[dict[str, Any]] | None = None,
        process_name: str | None = None,
        capture_width: int | None = None,
        capture_height: int | None = None,
        capture_origin_x: int | None = None,
        capture_origin_y: int | None = None,
        capture_mode: str = "window",
        capture_screen_origin_x: int | None = None,
        capture_screen_origin_y: int | None = None,
        capture_windows: list[dict[str, Any]] | None = None,
        supported_os: list[str] | None = None,
        safety_limits: dict[str, Any] | None = None,
    ) -> AnchorsContract:
        """创建并保存锚点配置。

        Args:
            profile_id: 配置 ID。
            title_contains: 窗口标题匹配文本。
            anchors: 锚点原始数据。
            process_name: 可选进程名。
            capture_width: 校准截图宽度。
            capture_height: 校准截图高度。
            capture_origin_x: 兼容旧窗口模式的截图原点 X 偏移。
            capture_origin_y: 兼容旧窗口模式的截图原点 Y 偏移。
            capture_mode: 截图坐标模式。
            capture_screen_origin_x: 校准截图画布在屏幕上的左上角 X。
            capture_screen_origin_y: 校准截图画布在屏幕上的左上角 Y。
            capture_windows: 参与截图的窗口元数据。
            supported_os: 支持的操作系统。
            safety_limits: 安全限制。

        Returns:
            已保存的锚点契约。
        """

        profile_id = require_valid_device_id(profile_id)
        profile = AnchorsContract(
            profile_id=profile_id,
            window_signature=WindowSignature(
                title_contains=title_contains,
                process_name=process_name,
                screenshot_size={
                    "width": capture_width,
                    "height": capture_height,
                },
                capture_origin_x=capture_origin_x or 0,
                capture_origin_y=capture_origin_y or 0,
                capture_mode=capture_mode,
                capture_screen_origin_x=capture_screen_origin_x,
                capture_screen_origin_y=capture_screen_origin_y,
                capture_windows=capture_windows or [],
            ),
            anchors=[self._coerce_anchor(anchor) for anchor in (anchors or [])],
            views=views or [],
            supported_os=supported_os or ["windows"],
            safety_limits=safety_limits or {},
        )
        self._logger.info("创建锚点配置: profile_id=%s, 窗口=%s, 锚点数=%d",
                          profile_id, title_contains, len(profile.anchors))
        self.save_profile(profile)
        return profile

    def save_profile(self, profile: AnchorsContract) -> Path:
        """保存锚点配置。

        Args:
            profile: 锚点契约。

        Returns:
            保存路径。
        """

        profile.exception_rules = [
            ExceptionRule.model_validate(rule)
            for rule in profile.exception_rules
        ]
        self._profiles[profile.profile_id] = profile
        path = dump_yaml_contract(profile, self._profile_path(profile.profile_id))
        self._logger.info("锚点配置已保存: profile_id=%s, 锚点数=%d",
                          profile.profile_id, len(profile.anchors))
        return path

    def get_profile(self, profile_id: str | None) -> AnchorsContract | None:
        """读取指定锚点配置。"""

        if not profile_id:
            return None
        return self._profiles.get(profile_id)

    def list_profiles(self) -> list[AnchorsContract]:
        """列出全部锚点配置。"""

        return list(self._profiles.values())

    def delete_profile(self, profile_id: str) -> None:
        """删除锚点配置。"""

        self._profiles.pop(profile_id, None)
        path = self._profile_path(profile_id)
        if path.parent.exists():
            shutil.rmtree(path.parent)
        self._logger.info("锚点配置已删除: profile_id=%s", profile_id)

    def save_capture(
        self,
        profile_id: str,
        data: bytes,
        *,
        view_id: str | None = None,
    ) -> Path:
        """保存设备校准截图。

        Args:
            profile_id: 锚点配置 ID。
            data: PNG 截图字节。

        Returns:
            已保存截图路径。
        """

        path = self._capture_path(profile_id, view_id=view_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def load_capture(
        self,
        profile_id: str | None,
        *,
        view_id: str | None = None,
    ) -> bytes | None:
        """读取设备校准截图。

        Args:
            profile_id: 锚点配置 ID。

        Returns:
            PNG 截图字节；不存在时返回 None。
        """

        if not profile_id:
            return None
        path = self._capture_path(profile_id, view_id=view_id)
        if not path.exists():
            return None
        return path.read_bytes()

    def delete_capture(self, profile_id: str, *, view_id: str | None = None) -> None:
        """删除指定设备视图的校准截图。

        Args:
            profile_id: 锚点配置 ID。
            view_id: 视图 ID；为空或 main 时删除主截图。
        """

        path = self._capture_path(profile_id, view_id=view_id)
        if view_id and view_id != "main":
            view_dir = path.parent
            if view_dir.exists():
                shutil.rmtree(view_dir)
            return
        if path.exists():
            path.unlink()

    def _profile_path(self, profile_id: str) -> Path:
        """返回锚点配置路径。"""

        return self._workspace_dir / "anchors" / profile_id / "anchors.yaml"

    def _capture_path(self, profile_id: str, *, view_id: str | None = None) -> Path:
        """返回设备校准截图路径。"""

        if not view_id or view_id == "main":
            return self._workspace_dir / "anchors" / profile_id / "capture.png"
        return self._workspace_dir / "anchors" / profile_id / "views" / view_id / "capture.png"

    @staticmethod
    def _coerce_anchor(raw: dict[str, Any]) -> AnchorDefinition:
        """把 UI 原始锚点数据转换为契约锚点。"""

        return AnchorDefinition.model_validate(raw)
