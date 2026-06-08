"""TemplateService: publish, version, fetch, and roll back templates.

A standardized workflow is published to the SpecLabOS template center via the
:class:`PlatformClient` port. SmartAccess keeps a local executable copy so a
platform outage never strands a runnable template (SPEC §5.2, §5.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from smartaccess.runtime.application.ports import PlatformClient, TemplateVersionMissing
from smartaccess.runtime.domain.template import TemplateIdentity, TemplateVersionStatus
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events import EventBus, RuntimeEventName


@dataclass(slots=True)
class TemplateRecord:
    """A published, local-only, cloud, superseded, or rolled-back template version."""

    identity: TemplateIdentity
    status: TemplateVersionStatus
    instrument_profile: str
    source: str
    published_at: str
    error: str = ""


@dataclass(slots=True)
class TemplateStats:
    """Local and cloud template counts for dashboards."""

    local_count: int = 0
    cloud_count: int = 0
    failed_count: int = 0
    cloud_available: bool = False


class TemplateService:
    """Manages the local view of the SpecLabOS template center."""

    def __init__(
        self,
        *,
        platform: PlatformClient,
        workspace_dir: Path,
        event_bus: EventBus,
    ) -> None:
        self._platform = platform
        self._workspace_dir = Path(workspace_dir)
        self._event_bus = event_bus
        self._records: dict[str, list[TemplateRecord]] = {}
        self._last_cloud_count = 0
        self._cloud_available = False
        self.load_all()
        self.refresh_cloud_index()

    def load_all(self) -> None:
        """Scan all local template workflow YAML files into the version index."""

        for path in sorted((self._workspace_dir / "templates").glob("*/*/workflow.yaml")):
            try:
                workflow = load_yaml_contract(path, WorkflowContract)
            except Exception:
                continue
            meta = workflow.metadata
            if not meta.template_id or not meta.template_version:
                continue
            record = TemplateRecord(
                identity=TemplateIdentity(meta.template_id, meta.template_version),
                status=TemplateVersionStatus.PUBLISHED if meta.lifecycle_state == "Published" else TemplateVersionStatus.DRAFT,
                instrument_profile=meta.instrument_profile,
                source="local",
                published_at="",
            )
            self._upsert(record)

    def refresh_cloud_index(self) -> TemplateStats:
        """Refresh cloud template count from SpecLabOS when the client supports it."""

        try:
            cloud_templates = self._platform.list_templates()
        except Exception:
            self._cloud_available = False
            return self.stats()
        self._cloud_available = True
        self._last_cloud_count = len(cloud_templates)
        for item in cloud_templates:
            template_id = str(item.get("template_id") or "").strip()
            template_version = str(item.get("template_version") or item.get("version") or "").strip()
            if not template_id or not template_version:
                continue
            self._upsert(
                TemplateRecord(
                    identity=TemplateIdentity(template_id, template_version),
                    status=TemplateVersionStatus.PUBLISHED,
                    instrument_profile=str(item.get("instrument_profile") or ""),
                    source="cloud",
                    published_at=str(item.get("published_at") or ""),
                )
            )
        return self.stats()

    def stats(self) -> TemplateStats:
        records = self.list_all()
        return TemplateStats(
            local_count=sum(1 for r in records if r.source in {"local", "smartaccess"}),
            cloud_count=self._last_cloud_count,
            failed_count=sum(1 for r in records if r.error),
            cloud_available=self._cloud_available,
        )

    def publish(self, workflow: WorkflowContract, *, source: str = "smartaccess") -> TemplateRecord:
        """Publish a standardized workflow and keep a local executable copy."""

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
                    "instrument_profile": meta.instrument_profile,
                    "workflow": workflow.model_dump(mode="json", exclude_none=True),
                }
            )
        except Exception as exc:
            error = str(exc)
            status = TemplateVersionStatus.DRAFT

        for record in self._records.get(identity.template_id, []):
            if record.status == TemplateVersionStatus.PUBLISHED:
                record.status = TemplateVersionStatus.SUPERSEDED

        record = TemplateRecord(
            identity=identity,
            status=status,
            instrument_profile=meta.instrument_profile,
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
        return list(self._records.get(template_id, []))

    def list_all(self) -> list[TemplateRecord]:
        return [record for records in self._records.values() for record in records]

    def rollback(self, template_id: str, template_version: str) -> TemplateRecord:
        """Roll the active template back to a previously published version."""

        records = self._records.get(template_id, [])
        target = next(
            (r for r in records if r.identity.template_version == template_version),
            None,
        )
        if target is None:
            raise TemplateVersionMissing(template_id, template_version)
        for record in records:
            if record.status == TemplateVersionStatus.PUBLISHED:
                record.status = TemplateVersionStatus.ROLLED_BACK
        target.status = TemplateVersionStatus.PUBLISHED
        return target

    def fetch(self, template_id: str, template_version: str) -> WorkflowContract:
        """Load the local executable copy of a template version."""

        path = self._template_path(TemplateIdentity(template_id, template_version))
        if not path.exists():
            raise TemplateVersionMissing(template_id, template_version)
        return load_yaml_contract(path, WorkflowContract)

    def _upsert(self, record: TemplateRecord) -> None:
        records = self._records.setdefault(record.identity.template_id, [])
        for idx, existing in enumerate(records):
            if existing.identity.template_version == record.identity.template_version and existing.source == record.source:
                records[idx] = record
                return
        records.append(record)

    def _template_path(self, identity: TemplateIdentity) -> Path:
        return (
            self._workspace_dir
            / "templates"
            / identity.template_id
            / identity.template_version
            / "workflow.yaml"
        )
