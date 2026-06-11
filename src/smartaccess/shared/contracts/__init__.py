"""Shared contract models and serialization helpers."""

from .anchors import (
    AnchorDefinition,
    AnchorActionBinding,
    AnchorRegion,
    AnchorsContract,
    NormalizedRegion,
    PixelRegion,
    ScreenshotSize,
    WindowSignature,
)
from .edge_api import ApiResponse, ExecuteRequest, HealthResponse, StatusResponse, TriggerGenerateRequest
from .eval_case import EvalCaseContract, EvalFixtures, EvalInputs, EvalScenario, ExpectedEventEntry
from .io import dump_jsonl_contracts, dump_yaml_contract, load_jsonl_contracts, load_yaml_contract
from .platform_adapter import AdapterRetryPolicy, AuthConfig, EndpointMap, PlatformAdapterContract
from .run_trace import ActionPayload, ErrorPayload, RunTraceRecord, WaitStrategyPayload
from .validation import validate_workflow_against_anchors
from .workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowRetryPolicy,
    WorkflowStep,
    WorkflowMigrationError,
)

__all__ = [
    "ActionPayload",
    "AdapterRetryPolicy",
    "AnchorDefinition",
    "AnchorActionBinding",
    "AnchorRegion",
    "AnchorsContract",
    "ApiResponse",
    "AuthConfig",
    "EndpointMap",
    "ErrorPayload",
    "EvalCaseContract",
    "EvalFixtures",
    "EvalInputs",
    "EvalScenario",
    "ExecuteRequest",
    "ExpectedEventEntry",
    "HealthResponse",
    "NormalizedRegion",
    "PixelRegion",
    "PlatformAdapterContract",
    "RunTraceRecord",
    "ScreenshotSize",
    "StatusResponse",
    "TriggerGenerateRequest",
    "WaitStrategyPayload",
    "WindowSignature",
    "WorkflowContract",
    "WorkflowMetadata",
    "WorkflowMigrationError",
    "WorkflowOutput",
    "WorkflowRetryPolicy",
    "WorkflowStep",
    "validate_workflow_against_anchors",
    "dump_jsonl_contracts",
    "dump_yaml_contract",
    "load_jsonl_contracts",
    "load_yaml_contract",
]
