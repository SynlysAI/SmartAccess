"""Workflow design view model: AI draft generation and standardization."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess.runtime.application.workflow_service import StandardizationResult
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract
from smartaccess.shared.contracts.workflow import WorkflowContract

from .base import ViewModel


class WorkflowViewModel(ViewModel):
    generated = pyqtSignal(object)  # WorkflowContract

    def list_workflows(self) -> list[WorkflowContract]:
        return self._facade.list_workflows()

    def reasoning(self) -> str:
        return self._facade.workflow_reasoning()

    def generator_label(self) -> str:
        return self._facade.workflow_generator_label()

    def list_instrument_ids(self) -> list[str]:
        return [p.device_id for p in self._facade.list_instruments()]

    def get_instrument(self, device_id: str | None) -> InstrumentProfileContract | None:
        return self._facade.get_instrument(device_id) if device_id else None

    def list_anchor_ids(self, device_id: str | None) -> list[str]:
        profile = self.get_instrument(device_id)
        return [anchor.id for anchor in profile.anchors] if profile else []

    def generate(self, prompt: str, *, device_id: str | None, workflow_id: str) -> WorkflowContract:
        profile = self._facade.get_instrument(device_id) if device_id else None
        context = {
            "workflow_id": workflow_id,
            "instrument_profile": device_id or "unknown_device",
        }
        if profile is not None:
            context["anchors"] = [a.model_dump(mode="json", exclude_none=True) for a in profile.anchors]
            context["actions"] = list(profile.actions)
            context["safety_limits"] = profile.safety_limits.model_dump(mode="json", exclude_none=True)
        workflow = self._facade.generate_workflow(prompt, context)
        self.generated.emit(workflow)
        self.changed.emit()
        return workflow

    def standardize(self, workflow: WorkflowContract) -> StandardizationResult:
        return self._facade.standardize(workflow)

    def save_workflow(self, workflow: WorkflowContract) -> WorkflowContract:
        saved = self._facade.update_workflow(workflow)
        self.changed.emit()
        return saved
