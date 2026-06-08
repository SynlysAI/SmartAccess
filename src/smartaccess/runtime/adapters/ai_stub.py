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

    def __init__(self) -> None:
        self.last_reasoning: str = ""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        instrument = context.get("instrument_profile") or "unknown_device"
        anchors = context.get("anchors") or []
        actions = context.get("actions") or []
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
        self.last_reasoning = self._explain(prompt, instrument, anchors, actions, steps, roi_bindings)
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

    @staticmethod
    def _explain(prompt, instrument, anchors, actions, steps, roi_bindings) -> str:
        """A human-readable trace of how this draft was assembled (item 13).

        The template generator is deterministic, so we narrate the same logic it
        applied — what context it read and why each step was chosen.
        """

        anchor_ids = [a.get("id") for a in anchors] if anchors else []
        lines = [
            "## 编排推理过程（模板生成器）",
            f"**目标描述**：{prompt.strip() or '（空）'}",
            f"**目标仪器**：`{instrument}`",
            "",
            "### 1. 读取上下文",
            f"- 可用锚点 {len(anchor_ids)} 个：{', '.join(anchor_ids) if anchor_ids else '（未提供，使用占位锚点）'}",
            f"- 已声明能力：{', '.join(actions) if actions else '（未提供）'}",
            "",
            "### 2. 步骤编排依据",
            "- 先打开方法编辑器，确保参数面板可见；",
            "- 再写入目标参数（type 动作绑定输入框锚点）；",
            "- 然后触发启动（高风险，保留原始 step id 供人工确认）；",
            "- 最后用 wait_until 轮询状态观测区，确认运行已开始。",
            "",
            "### 3. ROI / 输出绑定",
            *[f"- `{k}` → `{v}`" for k, v in roi_bindings.items()],
            "",
            f"### 4. 生成 {len(steps)} 个步骤的草稿，等待标准化检查。",
        ]
        return "\n".join(lines)
