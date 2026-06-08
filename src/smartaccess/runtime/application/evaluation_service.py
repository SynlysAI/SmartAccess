"""EvaluationService: load and summarize harness eval cases.

Loads the scenario contracts under ``ai/harness/evals/cases`` and reports a
lightweight pass/fail summary. A full scenario runner against the live runtime
is future work; for now this validates the five key scenarios load and declare
pass criteria (SPEC §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smartaccess.shared.contracts.eval_case import EvalCaseContract
from smartaccess.shared.contracts.io import load_yaml_contract


@dataclass(slots=True)
class EvalResult:
    scenario_id: str
    title: str
    passed: bool
    detail: str


class EvaluationService:
    """Loads eval cases and produces structural pass/fail summaries."""

    def __init__(self, *, cases_dir: Path) -> None:
        self._cases_dir = Path(cases_dir)

    def list_cases(self) -> list[EvalCaseContract]:
        return [
            load_yaml_contract(path, EvalCaseContract)
            for path in sorted(self._cases_dir.glob("*.yaml"))
        ]

    def run_all(self) -> list[EvalResult]:
        results: list[EvalResult] = []
        for path in sorted(self._cases_dir.glob("*.yaml")):
            try:
                case = load_yaml_contract(path, EvalCaseContract)
            except Exception as exc:  # noqa: BLE001 - report load failures as fails
                results.append(
                    EvalResult(
                        scenario_id=path.stem,
                        title=path.name,
                        passed=False,
                        detail=f"加载失败: {exc}",
                    )
                )
                continue
            passed = bool(case.pass_criteria) and bool(case.expected_events)
            results.append(
                EvalResult(
                    scenario_id=case.scenario.id,
                    title=case.scenario.title,
                    passed=passed,
                    detail="ok" if passed else "缺少 expected_events 或 pass_criteria",
                )
            )
        return results
