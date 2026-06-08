"""Deterministic workflow-draft generator stub.

Stands in for the AI workflow designer. Produces a believable
:class:`WorkflowContract` draft from a natural-language prompt plus context
(instrument profile, ROI bindings) so the workflow design page is fully wired.
"""

from __future__ import annotations

from typing import Any

from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowRetryPolicy,
    WorkflowStep,
)


class TemplatePromptWorkflowGenerator:
    """Maps a prompt + context onto a draft workflow contract."""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        instrument = context.get("instrument_profile") or "unknown_device"
        roi_bindings = context.get("roi_bindings") or {
            "status_banner": "roi_status_text",
            "voltage_panel": "roi_voltage_value",
        }
        steps = context.get("steps") or [
            {"id": "open_method_editor", "action": "click", "target": "anchor_method_editor_button"},
            {"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "4.20"},
            {"id": "start_run", "action": "click", "target": "anchor_start_button"},
            {"id": "wait_running", "action": "wait_until", "target": "roi_status_text"},
        ]
        return WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id=context.get("workflow_id", "wf_draft"),
                author=context.get("author", "ai-assistant"),
                instrument_profile=instrument,
                experiment_type=context.get("experiment_type", "generic_experiment"),
                lifecycle_state="Draft",
            ),
            preconditions=[],
            roi_bindings=roi_bindings,
            steps=[WorkflowStep(**s) for s in steps],
            outputs=[
                WorkflowOutput(key="run_status", source="roi_status_text"),
                WorkflowOutput(key="final_voltage", source="roi_voltage_value"),
            ],
            retry_policy=WorkflowRetryPolicy(max_attempts=2),
        )
