"""In-memory adapter stubs for local development and tests.

These let the Edge API run without a live UDP process host or the production
local instruction parser. Swap them for concrete providers
(``UdpProcessExecutorClient`` and the real parser) in :mod:`smartaccess.bootstrap`.
"""

from __future__ import annotations

from typing import Any

from smartaccess.runtime.application.ports import GenerationResult, ProcessExecutionState


class EchoInstructionGenerator:
    """Derives instruction lines directly from the submitted plan text.

    Placeholder for the production plan-to-instruction parser; it keeps every
    non-empty line so the trigger flow returns something inspectable.
    """

    def generate(self, experiment_plan: str) -> GenerationResult:
        instructions = [line.strip() for line in experiment_plan.splitlines() if line.strip()]
        return GenerationResult(instructions=instructions)


class StubProcessExecutorClient:
    """No-op executor that reports an idle host and echoes execute calls."""

    def __init__(self) -> None:
        self.executed = False

    def execute_process(self) -> Any:
        self.executed = True
        return {"ok": True, "echo": "EXECUTE_PROCESS_FILE"}

    def read_execution_state(self) -> ProcessExecutionState:
        return ProcessExecutionState(
            status="success",
            detail="stub executor: 当前没有流程在执行",
            current_command="",
        )

