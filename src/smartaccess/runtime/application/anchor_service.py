"""锚点配置服务。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from smartaccess.shared.contracts.anchors import (
    ACTION_SUPPORT_SETS,
    AnchorActionBinding,
    AnchorDefinition,
    AnchorRegion,
    AnchorsContract,
    NormalizedRegion,
    PixelRegion,
    SIMPLIFIED_ACTIONS,
    WindowSignature,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
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
            supported_os: 支持的操作系统。
            safety_limits: 安全限制。

        Returns:
            已保存的锚点契约。
        """

        profile = AnchorsContract(
            profile_id=profile_id,
            window_signature=WindowSignature(
                title_contains=title_contains,
                process_name=process_name,
                screenshot_size={
                    "width": capture_width,
                    "height": capture_height,
                },
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

        if "action_region" in raw:
            return AnchorService._simplify_anchor(AnchorDefinition.model_validate(raw))
        roi = raw.get("roi") or {}
        normalized = raw.get("normalized_roi") or {}
        action_bindings = raw.get("action_bindings") or []
        main_action = raw.get("main_action")
        if not main_action and action_bindings:
            main_action = action_bindings[0].get("action")
        if main_action not in SIMPLIFIED_ACTIONS:
            main_action = "click"
        supported_actions = ACTION_SUPPORT_SETS[main_action]
        requires_confirmation = bool(raw.get("requires_confirmation"))
        if action_bindings:
            requires_confirmation = any(
                bool(binding.get("requires_confirmation"))
                for binding in action_bindings
            )
        observe_region = AnchorService._observe_region(raw, roi, normalized)
        return AnchorService._simplify_anchor(
            AnchorDefinition(
                id=raw["id"],
                label=raw.get("label") or raw["id"],
                action_region=AnchorRegion(
                    pixel=PixelRegion(**roi),
                    normalized=(
                        NormalizedRegion(**normalized)
                        if normalized
                        else NormalizedRegion()
                    ),
                ),
                observe_region=observe_region,
                supported_actions=supported_actions,
                default_wait_seconds=float(raw.get("default_wait_seconds", 2.0)),
                notes=raw.get("notes"),
                type=raw.get("type"),
                locator_hint=raw.get("locator_hint"),
                vision_mode=raw.get("vision_mode"),
                action_bindings=[
                    {
                        "action": action,
                        "requires_confirmation": requires_confirmation,
                    }
                    for action in supported_actions
                ],
            )
        )

    @staticmethod
    def _observe_region(
        raw: dict[str, Any],
        roi: dict[str, Any],
        normalized: dict[str, Any],
    ) -> AnchorRegion | None:
        """从原始数据中提取观察区域。"""

        observe_roi = raw.get("observe_roi") or raw.get("observe_region")
        observe_normalized = raw.get("observe_normalized_roi")
        vision_mode = raw.get("vision_mode") or ("ocr" if observe_roi else "none")
        if vision_mode != "ocr":
            return None
        observe_pixel = (
            observe_roi.get("pixel")
            if isinstance(observe_roi, dict) and "pixel" in observe_roi
            else observe_roi or roi
        )
        observe_norm = (
            observe_roi.get("normalized")
            if isinstance(observe_roi, dict) and "normalized" in observe_roi
            else observe_normalized or normalized
        )
        return AnchorRegion(
            pixel=PixelRegion(**(observe_pixel or {})),
            normalized=(
                NormalizedRegion(**observe_norm) if observe_norm else NormalizedRegion()
            ),
        )

    @staticmethod
    def _simplify_anchor(anchor: AnchorDefinition) -> AnchorDefinition:
        """清理锚点动作绑定和视觉字段。"""

        supported_actions = [
            action for action in anchor.supported_actions if action in SIMPLIFIED_ACTIONS
        ] or ["click"]
        requires_confirmation = any(
            binding.requires_confirmation
            for binding in anchor.action_bindings
            if binding.action in supported_actions
        )
        anchor.supported_actions = list(dict.fromkeys(supported_actions))
        anchor.action_bindings = [
            AnchorActionBinding(
                action=action,
                requires_confirmation=requires_confirmation,
            )
            for action in anchor.supported_actions
        ]
        anchor.type = "observation" if anchor.observe_region is not None else "action_target"
        anchor.vision_mode = "ocr" if anchor.observe_region is not None else None
        anchor.confidence_threshold = None
        anchor.vision_config = None
        return anchor
