"""RuntimeFacade: the single in-process entry point the desktop talks to.

Holds every application service, the shared event bus, and the orchestrator,
and exposes coarse-grained use-case methods. This is the seam that a future
HTTP Internal Control API would wrap — the desktop depends only on this, never
on concrete providers (software-design §3.3, §4.4).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from smartaccess.runtime.application.calibration_service import CalibrationService
from smartaccess.runtime.application.evaluation_service import EvalResult, EvaluationService
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.run_session_service import RunSessionService
from smartaccess.runtime.application.template_service import TemplateRecord, TemplateService
from smartaccess.runtime.application.workflow_service import (
    StandardizationResult,
    WorkflowService,
)
from smartaccess.runtime.application.workspace_service import (
    DashboardProjection,
    WorkspaceService,
)
from smartaccess.runtime.domain.incident import RecoveryAction
from smartaccess.runtime.domain.run_session import RunSession, RunStep
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState
from smartaccess.runtime.orchestration import (
    Executor,
    Observer,
    Orchestrator,
    RecoveryEngine,
)
from smartaccess.runtime.orchestration.orchestrator import ConfirmRequest
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.events import EventBus, Subscriber

ConfirmHandler = Callable[[ConfirmRequest], bool]


class RuntimeFacade:
    """Coarse-grained use-case surface for the desktop shell."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        calibration: CalibrationService,
        workflow: WorkflowService,
        template: TemplateService,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        platform_sync: PlatformSyncService,
        workspace: WorkspaceService,
        evaluation: EvaluationService,
        executor: Executor,
        observer: Observer,
        recovery: RecoveryEngine,
        max_retries: int = 2,
    ) -> None:
        self._event_bus = event_bus
        self._calibration = calibration
        self._workflow = workflow
        self._template = template
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._platform_sync = platform_sync
        self._workspace = workspace
        self._evaluation = evaluation
        self._confirm_handler: ConfirmHandler = lambda _request: True
        self._orchestrator = Orchestrator(
            executor=executor,
            observer=observer,
            recovery=recovery,
            run_sessions=run_sessions,
            incidents=incidents,
            confirm_handler=lambda request: self._confirm_handler(request),
            max_retries=max_retries,
        )

    # --- events ------------------------------------------------------- #
    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        return self._event_bus.subscribe(callback)

    def set_confirm_handler(self, handler: ConfirmHandler) -> None:
        self._confirm_handler = handler

    # --- dashboard ---------------------------------------------------- #
    def dashboard(self) -> DashboardProjection:
        return self._workspace.dashboard()

    # --- calibration -------------------------------------------------- #
    def discover_windows(self):
        return self._calibration.discover_windows()

    def capture_window(self, hwnd: int) -> bytes | None:
        return self._calibration.capture_window(hwnd)

    def create_calibration(self, **kwargs: Any) -> InstrumentProfileContract:
        profile = self._calibration.create_profile(**kwargs)
        self._calibration.activate(profile.device_id)
        return profile

    def list_instruments(self) -> list[InstrumentProfileContract]:
        return self._calibration.list_profiles()

    def get_instrument(self, device_id: str | None) -> InstrumentProfileContract | None:
        return self._calibration.get_profile(device_id) if device_id else None

    # --- workflow ----------------------------------------------------- #
    def generate_workflow(self, prompt: str, context: dict[str, Any] | None = None) -> WorkflowContract:
        return self._workflow.draft_from_prompt(prompt, context or {})

    def workflow_reasoning(self) -> str:
        return self._workflow.last_reasoning()

    def workflow_generator_label(self) -> str:
        return self._workflow.generator_label()

    def register_workflow(self, workflow: WorkflowContract) -> WorkflowContract:
        return self._workflow.register(workflow)

    def update_workflow(self, workflow: WorkflowContract) -> WorkflowContract:
        return self._workflow.update(workflow)

    def list_workflows(self) -> list[WorkflowContract]:
        return self._workflow.list_workflows()

    def standardize(self, workflow: WorkflowContract) -> StandardizationResult:
        return self._workflow.standardize_check(workflow)

    def transition_workflow(
        self, workflow: WorkflowContract, target: WorkflowLifecycleState
    ) -> WorkflowContract:
        return self._workflow.transition(workflow, target)

    # --- templates ---------------------------------------------------- #
    def publish_template(self, workflow: WorkflowContract) -> TemplateRecord:
        return self._template.publish(workflow)

    def list_templates(self) -> list[TemplateRecord]:
        return self._template.list_all()

    def template_stats(self):
        return self._template.stats()

    def refresh_cloud_templates(self):
        return self._template.refresh_cloud_index()

    def rollback_template(self, template_id: str, template_version: str) -> TemplateRecord:
        return self._template.rollback(template_id, template_version)

    def fetch_template(self, template_id: str, template_version: str) -> WorkflowContract:
        return self._template.fetch(template_id, template_version)

    # --- runs --------------------------------------------------------- #
    def start_run(
        self,
        *,
        workflow: WorkflowContract | None = None,
        workflow_id: str | None = None,
        device_id: str | None = None,
        background: bool = False,
    ) -> RunSession:
        wf = workflow or (self._workflow.get(workflow_id) if workflow_id else None)
        if wf is None:
            raise ValueError("start_run 需要 workflow 或可解析的 workflow_id")

        profile = None
        target_device = device_id or wf.metadata.instrument_profile
        if target_device:
            profile = self._calibration.get_profile(target_device)

        session = self._run_sessions.create_session(
            wf.metadata.workflow_id,
            steps=[RunStep(step_id=s.id, action=s.action) for s in wf.steps],
            template_id=wf.metadata.template_id,
            template_version=wf.metadata.template_version,
        )

        if background:
            thread = threading.Thread(
                target=self._orchestrator.run,
                kwargs={"workflow": wf, "profile": profile, "session": session},
                daemon=True,
            )
            thread.start()
        else:
            self._orchestrator.run(workflow=wf, profile=profile, session=session)
        return session

    def confirm_incident(self, incident_id: str, *, action: RecoveryAction | None = None):
        return self._incidents.confirm(incident_id, action=action)

    def get_trace(self, session_id: str):
        return self._run_sessions.get_trace(session_id)

    # --- platform / evals --------------------------------------------- #
    def sync_platform(self):
        return self._platform_sync.sync()

    def run_evals(self) -> list[EvalResult]:
        return self._evaluation.run_all()
