"""模板发布和本地版本索引服务。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from smartaccess_v2.runtime.application.ports import (
    PlatformClient,
    TemplateVersionMissing,
)
from smartaccess_v2.runtime.domain.template import (
    TemplateIdentity,
    TemplateVersionStatus,
)
from smartaccess_v2.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess_v2.shared.contracts.workflow import WorkflowContract
from smartaccess_v2.shared.events.bus import EventBus
from smartaccess_v2.shared.events.runtime import RuntimeEventName
from smartaccess_v2.shared.logging import get_logger


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
            workspace_dir: v2 工作区目录。
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

    def refresh_cloud_index(self) -> TemplateStats:
        """刷新平台模板索引。"""

        try:
            cloud_templates = self._platform.list_templates()
        except Exception:  # noqa: BLE001 - 平台不可用不影响本地模板
            self._cloud_available = False
            return self.stats()
        self._cloud_available = True
        self._last_cloud_count = len(cloud_templates)
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
            raise RuntimeError(f"模板已保存到本地，但发布到 SpecLabOS 失败: {error}")
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
        return target

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
