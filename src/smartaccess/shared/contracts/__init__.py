"""Shared contract models and serialization helpers."""

from .edge_api import ApiResponse, ExecuteRequest, HealthResponse, StatusResponse, TriggerGenerateRequest
from .eval_case import EvalCaseContract, EvalFixtures, EvalInputs, EvalScenario, ExpectedEventEntry
from .instrument_profile import (
    ActionBinding,
    AnchorDefinition,
    InstrumentProfileContract,
    NormalizedRoiRect,
    RoiRect,
    SafetyField,
    SafetyLimits,
    WindowSignature,
)
from .io import dump_jsonl_contracts, dump_yaml_contract, load_jsonl_contracts, load_yaml_contract
from .platform_adapter import AdapterRetryPolicy, AuthConfig, EndpointMap, PlatformAdapterContract
from .run_trace import ActionPayload, ArtifactPayload, ObservationPayload, ResultPayload, RunTraceRecord
from .workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowPrecondition,
    WorkflowRetryPolicy,
    WorkflowStep,
)

__all__ = [
    "ActionBinding",
    "ActionPayload",
    "AdapterRetryPolicy",
    "AnchorDefinition",
    "ApiResponse",
    "ArtifactPayload",
    "AuthConfig",
    "EndpointMap",
    "EvalCaseContract",
    "EvalFixtures",
    "EvalInputs",
    "EvalScenario",
    "ExecuteRequest",
    "ExpectedEventEntry",
    "HealthResponse",
    "InstrumentProfileContract",
    "NormalizedRoiRect",
    "ObservationPayload",
    "PlatformAdapterContract",
    "ResultPayload",
    "RoiRect",
    "RunTraceRecord",
    "SafetyField",
    "SafetyLimits",
    "StatusResponse",
    "TriggerGenerateRequest",
    "WindowSignature",
    "WorkflowContract",
    "WorkflowMetadata",
    "WorkflowOutput",
    "WorkflowPrecondition",
    "WorkflowRetryPolicy",
    "WorkflowStep",
    "dump_jsonl_contracts",
    "dump_yaml_contract",
    "load_jsonl_contracts",
    "load_yaml_contract",
]
