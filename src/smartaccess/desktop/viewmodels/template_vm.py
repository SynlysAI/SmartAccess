"""Template library view model: publish, list, rollback."""

from __future__ import annotations

from smartaccess.runtime.application.template_service import TemplateRecord, TemplateStats
from smartaccess.shared.contracts.workflow import WorkflowContract

from .base import ViewModel


class TemplateViewModel(ViewModel):
    def list_templates(self) -> list[TemplateRecord]:
        return self._facade.list_templates()

    def search_templates(self, query: str = "", status: str = "") -> list[TemplateRecord]:
        return self._facade.search_templates(query, status)

    def stats(self) -> TemplateStats:
        return self._facade.template_stats()

    def refresh_cloud(self) -> TemplateStats:
        return self._facade.refresh_cloud_templates()

    def publishable_workflows(self) -> list[WorkflowContract]:
        return self._facade.list_workflows()

    def publish(self, workflow: WorkflowContract) -> TemplateRecord:
        record = self._facade.publish_template(workflow)
        self.changed.emit()
        return record

    def rollback(self, template_id: str, template_version: str) -> TemplateRecord:
        record = self._facade.rollback_template(template_id, template_version)
        self.changed.emit()
        return record

    def update_version(self, template_id: str, template_version: str, *, instrument_profile: str) -> TemplateRecord:
        record = self._facade.update_template_version(
            template_id, template_version, instrument_profile=instrument_profile
        )
        self.changed.emit()
        return record

    def delete_version(self, template_id: str, template_version: str, *, force: bool = False) -> TemplateRecord:
        record = self._facade.delete_template_version(template_id, template_version, force=force)
        self.changed.emit()
        return record
