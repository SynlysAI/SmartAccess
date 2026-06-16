"""模板发布和本地版本索引服务。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from smartaccess.runtime.application.ports import (
    PlatformClient,
    TemplateVersionMissing,
)
from smartaccess.runtime.domain.template import (
    TemplateIdentity,
    TemplateVersionStatus,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events.bus import EventBus
from smartaccess.shared.events.runtime import RuntimeEventName
from smartaccess.shared.logging import get_logger


@dataclass(slots=True)
class TemplateRecord:
    """模板版本记录。"""

    identity: TemplateIdentity
    status: TemplateVersionStatus
    anchor_profile: str
    source: str
    published_at: str
    error: str = ""


@dataclass(slots=True)
class TemplateStats:
    """模板统计信息。"""

    local_count: int = 0
    cloud_count: int = 0
    failed_count: int = 0
    cloud_available: bool = False


class TemplateService:
    """管理本地模板和平台模板索引。"""

    def __init__(
        self,
        *,
        platform: PlatformClient,
        workspace_dir: Path,
        event_bus: EventBus,
    ) -> None:
        """初始化模板服务。

        Args:
            platform: 平台客户端。
            workspace_dir: 工作区目录。
            event_bus: 运行时事件总线。
        """

        self._platform = platform
        self._workspace_dir = Path(workspace_dir)
        self._event_bus = event_bus
        self._records: dict[str, list[TemplateRecord]] = {}
        self._last_cloud_count = 0
        self._cloud_available = False
        self._logger = get_logger()
        self.load_all()
        self.refresh_cloud_index()

    def load_all(self) -> None:
        """加载本地模板工作流。"""

        self._records.clear()
        loaded_count = 0
        for path in sorted((self._workspace_dir / "templates").glob("*/*/workflow.yaml")):
            try:
                workflow = load_yaml_contract(path, WorkflowContract)
            except Exception:  # noqa: BLE001 - 单个坏文件不能阻断启动
                self._logger.exception("模板加载失败: %s", path)
                continue
            meta = workflow.metadata
            if not meta.template_id or not meta.template_version:
                continue
            record = TemplateRecord(
                identity=TemplateIdentity(meta.template_id, meta.template_version),
                status=(
                    TemplateVersionStatus.PUBLISHED
                    if meta.lifecycle_state == "Published"
                    else TemplateVersionStatus.DRAFT
                ),
                anchor_profile=meta.anchor_profile or "",
                source="local",
                published_at="",
            )
            self._upsert(record)
            loaded_count += 1
        if loaded_count:
            self._logger.info("已加载 %d 个本地模板", loaded_count)

    def refresh_cloud_index(self) -> TemplateStats:
        """刷新平台模板索引。"""

        try:
            cloud_templates = self._platform.list_templates()
        except Exception:  # noqa: BLE001 - 平台不可用不影响本地模板
            self._cloud_available = False
            return self.stats()
        self._cloud_available = True
        self._last_cloud_count = len(cloud_templates)
        self._logger.info("云端模板索引已刷新: 共 %d 个模板", self._last_cloud_count)
        for item in cloud_templates:
            template_id = str(item.get("template_id") or "").strip()
            template_version = str(
                item.get("template_version") or item.get("version") or ""
            ).strip()
            if not template_id or not template_version:
                continue
            self._upsert(
                TemplateRecord(
                    identity=TemplateIdentity(template_id, template_version),
                    status=TemplateVersionStatus.PUBLISHED,
                    anchor_profile=str(
                        item.get("anchor_profile")
                        or item.get("instrument_profile")
                        or ""
                    ),
                    source="cloud",
                    published_at=str(item.get("published_at") or ""),
                )
            )
        return self.stats()

    def stats(self) -> TemplateStats:
        """返回模板统计。"""

        records = self.list_all()
        return TemplateStats(
            local_count=sum(1 for item in records if item.source in {"local", "smartaccess"}),
            cloud_count=self._last_cloud_count,
            failed_count=sum(1 for item in records if item.error),
            cloud_available=self._cloud_available,
        )

    def publish(
        self,
        workflow: WorkflowContract,
        *,
        source: str = "smartaccess",
    ) -> TemplateRecord:
        """发布标准化工作流为模板。

        Args:
            workflow: 工作流契约。
            source: 模板来源。

        Returns:
            模板记录。
        """

        meta = workflow.metadata
        if not meta.template_id or not meta.template_version:
            raise ValueError("发布前必须填写 template_id 与 template_version")
        identity = TemplateIdentity(meta.template_id, meta.template_version)
        self._logger.info("发布模板: %s@%s", identity.template_id, identity.template_version)
        dump_yaml_contract(workflow, self._template_path(identity))
        error = ""
        status = TemplateVersionStatus.PUBLISHED
        try:
            self._platform.publish_template(
                {
                    "template_id": identity.template_id,
                    "template_version": identity.template_version,
                    "anchor_profile": meta.anchor_profile,
                    "workflow": workflow.model_dump(mode="json", exclude_none=True),
                }
            )
        except Exception as exc:  # noqa: BLE001 - 本地保存成功时记录平台错误
            error = str(exc)
            status = TemplateVersionStatus.DRAFT
        for record in self._records.get(identity.template_id, []):
            if record.status == TemplateVersionStatus.PUBLISHED:
                record.status = TemplateVersionStatus.SUPERSEDED
        record = TemplateRecord(
            identity=identity,
            status=status,
            anchor_profile=meta.anchor_profile or "",
            source=source,
            published_at=datetime.now(timezone.utc).isoformat(),
            error=error,
        )
        self._upsert(record)
        self._event_bus.emit(
            RuntimeEventName.TEMPLATE_PUBLISHED,
            template_id=identity.template_id,
            template_version=identity.template_version,
            error=error,
        )
        if error:
            self._logger.warning("模板发布到平台失败: %s", error)
            raise RuntimeError(f"模板已保存到本地，但发布到 SpecLabOS 失败: {error}")
        self._logger.info("模板发布成功: %s@%s", identity.template_id, identity.template_version)
        return record

    def list_versions(self, template_id: str) -> list[TemplateRecord]:
        """列出指定模板的版本。"""

        return list(self._records.get(template_id, []))

    def list_all(self) -> list[TemplateRecord]:
        """列出全部模板版本。"""

        return [record for records in self._records.values() for record in records]

    def search_templates(self, query: str = "", status: str = "") -> list[TemplateRecord]:
        """搜索模板记录。"""

        needle = query.strip().lower()
        wanted_status = status.strip().lower()
        records = self.list_all()
        if wanted_status and wanted_status != "all":
            records = [
                item for item in records if item.status.value.lower() == wanted_status
            ]
        if not needle:
            return records
        return [
            item
            for item in records
            if needle
            in " ".join(
                [
                    item.identity.template_id,
                    item.identity.template_version,
                    item.status.value,
                    item.anchor_profile,
                    item.source,
                    item.error,
                ]
            ).lower()
        ]

    def delete_version(
        self,
        template_id: str,
        template_version: str,
        *,
        force: bool = False,
    ) -> TemplateRecord:
        """删除本地模板版本。"""

        records = self._records.get(template_id, [])
        target = next(
            (
                item
                for item in records
                if item.identity.template_version == template_version
            ),
            None,
        )
        if target is None:
            raise TemplateVersionMissing(template_id, template_version)
        if target.status == TemplateVersionStatus.PUBLISHED and not force:
            raise ValueError("当前发布版本需要确认后才能删除")
        records.remove(target)
        path = self._template_path(target.identity)
        if path.exists():
            shutil.rmtree(path.parent)
        if not records:
            self._records.pop(template_id, None)
        self._logger.info("模板版本已删除: %s@%s", template_id, template_version)
        return target

    def update_version_metadata(
        self,
        template_id: str,
        template_version: str,
        *,
        anchor_profile: str | None = None,
    ) -> TemplateRecord:
        """更新模板版本元数据。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            anchor_profile: 新的设备锚点配置 ID。

        Returns:
            更新后的模板记录。
        """

        target = self._find_record(template_id, template_version)
        if anchor_profile is not None:
            target.anchor_profile = anchor_profile
            path = self._template_path(target.identity)
            if path.exists():
                workflow = load_yaml_contract(path, WorkflowContract)
                workflow.metadata.anchor_profile = anchor_profile
                dump_yaml_contract(workflow, path)
        return target

    def delete_version_cloud_first(
        self,
        template_id: str,
        template_version: str,
        *,
        force: bool = False,
    ) -> TemplateRecord:
        """先删除云端模板，再删除本地副本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            force: 是否允许删除已发布版本。

        Returns:
            已删除的模板记录。
        """

        target = self._find_record(template_id, template_version)
        if target.status == TemplateVersionStatus.PUBLISHED and not force:
            raise ValueError("当前发布版本需要 force=True 确认后才能删除")
        try:
            self._platform.delete_template(template_id, template_version)
        except TemplateVersionMissing:
            pass
        except Exception as exc:  # noqa: BLE001 - 云端失败时保留本地副本
            raise RuntimeError(
                f"云端删除模板 {template_id}@{template_version} 失败，本地副本已保留。"
            ) from exc
        return self.delete_version(template_id, template_version, force=True)

    def rollback(self, template_id: str, template_version: str) -> TemplateRecord:
        """回滚到指定模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            回滚后成为发布版本的模板记录。
        """

        records = self._records.get(template_id, [])
        target = self._find_record(template_id, template_version)
        for record in records:
            if record.status == TemplateVersionStatus.PUBLISHED:
                record.status = TemplateVersionStatus.ROLLED_BACK
        target.status = TemplateVersionStatus.PUBLISHED
        self._logger.info("模板已回滚: %s@%s", template_id, template_version)
        return target

    def fetch(self, template_id: str, template_version: str) -> WorkflowContract:
        """读取本地可执行模板工作流。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            工作流契约。
        """

        path = self._template_path(TemplateIdentity(template_id, template_version))
        if not path.exists():
            raise TemplateVersionMissing(template_id, template_version)
        return load_yaml_contract(path, WorkflowContract)

    def _template_path(self, identity: TemplateIdentity) -> Path:
        """返回模板工作流路径。"""

        return (
            self._workspace_dir
            / "templates"
            / identity.template_id
            / identity.template_version
            / "workflow.yaml"
        )

    def _upsert(self, record: TemplateRecord) -> None:
        """插入或更新模板记录。"""

        records = self._records.setdefault(record.identity.template_id, [])
        for index, existing in enumerate(records):
            if existing.identity.template_version == record.identity.template_version:
                records[index] = record
                return
        records.append(record)

    def _find_record(
        self,
        template_id: str,
        template_version: str,
    ) -> TemplateRecord:
        """查找模板版本记录。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            模板记录。
        """

        records = self._records.get(template_id, [])
        target = next(
            (
                item
                for item in records
                if item.identity.template_version == template_version
            ),
            None,
        )
        if target is None:
            raise TemplateVersionMissing(template_id, template_version)
        return target
