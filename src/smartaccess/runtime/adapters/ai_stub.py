"""Deterministic workflow-draft generator stub."""

from __future__ import annotations

from typing import Any

from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)


class TemplatePromptWorkflowGenerator:
    """Maps a prompt + context onto a v2 workflow contract."""

    def __init__(self) -> None:
        self.last_reasoning: str = ""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        anchor_profile = context.get("anchor_profile") or context.get("instrument_profile") or "unknown_device"
        anchors = context.get("anchors") or []
        actions = context.get("actions") or []
        prompt_references = context.get("prompt_references") or []
        anchor_ids = [anchor.get("id") for anchor in anchors if anchor.get("id")]

        default_steps = [
            {
                "id": "open_method_editor",
                "anchor_id": anchor_ids[0] if anchor_ids else "anchor_method_editor_button",
                "action": "click",
                "match_mode": "none",
                "wait_seconds": 1.0,
            },
            {
                "id": "input_target_value",
                "anchor_id": anchor_ids[1] if len(anchor_ids) > 1 else (anchor_ids[0] if anchor_ids else "anchor_value_input"),
                "action": "type",
                "value": "4.20",
                "match_mode": "none",
                "wait_seconds": 0.5,
            },
        ]
        if len(anchor_ids) > 2:
            default_steps.append(
                {
                    "id": "run_and_wait",
                    "anchor_id": anchor_ids[2],
                    "action": "click",
                    "expected_text": "Running",
                    "match_mode": "contains",
                    "timeout_seconds": 10.0,
                    "requires_confirmation": True,
                }
            )
        elif anchor_ids:
            default_steps[0]["expected_text"] = "OK"
            default_steps[0]["match_mode"] = "not_empty"
            default_steps[0]["timeout_seconds"] = 2.0
        steps = context.get("steps") or default_steps
        self.last_reasoning = self._explain(
            prompt=prompt,
            anchor_profile=anchor_profile,
            anchor_ids=anchor_ids,
            actions=actions,
            steps=steps,
            prompt_references=prompt_references,
        )
        return WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id=context.get("workflow_id", "wf_draft"),
                anchor_profile=anchor_profile,
                author=context.get("author", "ai-assistant"),
                lifecycle_state="Draft",
                template_id=context.get("template_id"),
                template_version=context.get("template_version"),
            ),
            steps=[WorkflowStep(**step) for step in steps],
        )

    @staticmethod
    def _explain(
        *,
        prompt: str,
        anchor_profile: str,
        anchor_ids: list[str],
        actions: list[str],
        steps: list[dict[str, Any]],
        prompt_references: list[dict[str, Any]],
    ) -> str:
        lines = [
            "## Draft reasoning",
            f"prompt: {prompt.strip() or '(empty)'}",
            f"anchor_profile: {anchor_profile}",
            f"anchors: {', '.join(anchor_ids) if anchor_ids else '(none)'}",
            f"actions: {', '.join(actions) if actions else '(none)'}",
            "",
            "### Prompt references",
        ]
        if prompt_references:
            lines.extend(
                f"- {item.get('token')} -> {item.get('category')} / {item.get('ref_id')}"
                for item in prompt_references
            )
        else:
            lines.append("- none")
        lines.extend(["", "### Steps"])
        for idx, step in enumerate(steps, 1):
            lines.append(
                f"{idx}. {step.get('id')} :: {step.get('action')} -> {step.get('anchor_id')}"
            )
        return "\n".join(lines)
