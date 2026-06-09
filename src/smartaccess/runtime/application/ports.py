"""Adapter-facing ports for the application layer.

Application services and the orchestration loop depend on these Protocols,
never on concrete providers. Concrete implementations (stub or real) live under
:mod:`smartaccess.runtime.adapters`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from smartaccess.shared.contracts.instrument_profile import AnchorDefinition, RoiRect
from smartaccess.shared.contracts.workflow import WorkflowContract


# --------------------------------------------------------------------------- #
# DTOs exchanged across the port boundary
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class GenerationResult:
    """Outcome of turning an experiment plan into local instructions."""

    instructions: list[str]


@dataclass(slots=True)
class ProcessExecutionState:
    """Normalized execution state read from the downstream process host."""

    status: str
    detail: str
    current_command: str


@dataclass(slots=True)
class WindowInfo:
    """A discovered instrument window."""

    title: str
    width: int = 0
    height: int = 0
    matched: bool = True
    hwnd: int | None = None


@dataclass(slots=True)
class OcrReading:
    """A single OCR/vision reading with provenance for the run trace."""

    roi: str
    text: str
    confidence: float
    source_path: str | None = None
    detail: str = ""


@dataclass(slots=True)
class ActionOutcome:
    """Result of running one action primitive through the automation provider."""

    ok: bool
    detail: str = ""
    screenshot_path: str | None = None


@dataclass(slots=True)
class Screenshot:
    """PNG screenshot bytes plus source dimensions."""

    data: bytes
    width: int = 0
    height: int = 0


# --------------------------------------------------------------------------- #
# Edge / experiment ports (used by the device-side Edge API)
# --------------------------------------------------------------------------- #
class InstructionGenerator(Protocol):
    """Turns an experiment plan into local execution instructions."""

    def generate(self, experiment_plan: str) -> GenerationResult: ...


class ProcessExecutorClient(Protocol):
    """Drives the downstream process host (e.g. an instrument via UDP)."""

    def execute_process(self) -> Any: ...

    def read_execution_state(self) -> ProcessExecutionState: ...


# --------------------------------------------------------------------------- #
# Runtime execution ports (used by the orchestration loop)
# --------------------------------------------------------------------------- #
class AutomationProvider(Protocol):
    """UI-level automation against an instrument upper-computer."""

    def window_present(self, title_contains: str | None) -> bool: ...

    def discover_windows(self) -> list[WindowInfo]: ...

    def locate_anchor(self, anchor_id: str) -> bool: ...

    def configure_profile(self, profile: Any | None) -> None: ...

    def run_action(
        self, action: str, target: str | None, value: Any | None
    ) -> ActionOutcome: ...

    def screenshot(self, label: str) -> bytes: ...

    def capture_window(self, hwnd: int) -> bytes | None: ...


class VisionProvider(Protocol):
    """Screenshot-based recognition: OCR, presence detection, template match."""

    def read_text(self, roi: str) -> OcrReading: ...

    def read_roi_text(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: RoiRect | None = None,
    ) -> OcrReading: ...

    def detect_presence(self, roi: str) -> bool: ...

    def match_template(self, roi: str) -> OcrReading: ...

    def sample_color(self, roi: str) -> OcrReading: ...


class PlatformClient(Protocol):
    """Isolates SpecLabOS interface differences (platform_adapter.yaml)."""

    def health(self) -> bool: ...

    def fetch_task(self) -> dict[str, Any] | None: ...

    def fetch_template(self, template_id: str, template_version: str) -> dict[str, Any]: ...

    def list_templates(self) -> list[dict[str, Any]]: ...

    def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def delete_template(self, template_id: str, template_version: str) -> bool: ...

    def upload_status(self, payload: dict[str, Any]) -> bool: ...

    def upload_logs(self, payload: dict[str, Any]) -> bool: ...

    def upload_results(self, payload: dict[str, Any]) -> bool: ...


class ArtifactStore(Protocol):
    """Stores screenshots, logs, and JSONL produced during a run."""

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str: ...

    def save_text(self, session_id: str, name: str, text: str) -> str: ...

    def append_jsonl(self, session_id: str, name: str, line: str) -> str: ...


class WorkflowDraftGenerator(Protocol):
    """Turns a natural-language prompt + context into a workflow draft."""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> Any: ...


class TemplateVersionMissing(Exception):
    """Raised by a platform client when a requested template version is absent."""

    def __init__(self, template_id: str, template_version: str) -> None:
        self.template_id = template_id
        self.template_version = template_version
        super().__init__(f"模板版本不存在: {template_id}@{template_version}")


class PlatformOffline(Exception):
    """Raised by a platform client when the platform is unreachable."""

    def __init__(self, detail: str = "platform offline") -> None:
        self.detail = detail
        super().__init__(detail)


# --------------------------------------------------------------------------- #
# Projection DTOs — UI-facing shapes derived from domain models
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class WorkflowListEntry:
    """Projection for the workflow list UI with source-kind differentiation."""

    workflow: WorkflowContract
    source_kind: str  # "draft" | "local_template"
    storage_ref: str  # filesystem path or template identity
    display_label: str


@dataclass(slots=True)
class InstrumentReferenceInfo:
    """Pre-check result before deleting an instrument profile."""

    device_id: str
    draft_count: int = 0
    local_template_count: int = 0
    active_session_count: int = 0
    referencing_workflow_ids: list[str] | None = None
    referencing_template_ids: list[str] | None = None
