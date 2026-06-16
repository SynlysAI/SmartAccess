"""旧工作区导入服务。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.logging import get_logger


@dataclass(slots=True)
class MigrationReport:
    """旧工作区导入报告。"""

    imported_anchors: int = 0
    imported_workflows: int = 0
    imported_templates: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def imported_total(self) -> int:
        """返回成功导入总数。"""

        return (
            self.imported_anchors
            + self.imported_workflows
            + self.imported_templates
        )


class MigrationService:
    """把旧 workspace 中可校验的数据导入 工作区。"""

    def __init__(self, *, workspace_dir: Path) -> None:
        """初始化迁移服务。

        Args:
            workspace_dir: 工作区目录。
        """

        self._workspace_dir = Path(workspace_dir)
        self._logger = get_logger()

    def import_legacy_workspace(
        self,
        legacy_workspace: str | Path = "workspace",
    ) -> MigrationReport:
        """导入旧工作区中的锚点、工作流和模板。

        Args:
            legacy_workspace: 旧工作区目录。

        Returns:
            导入报告。
        """

        source = Path(legacy_workspace)
        report = MigrationReport()
        if not source.exists():
            report.skipped.append(f"旧工作区不存在: {source}")
            return report
        self._logger.info("开始导入旧工作区: %s", source)
        self._import_anchors(source, report)
        self._import_workflows(source, report)
        self._import_templates(source, report)
        self._logger.info(
            "旧工作区导入完成: 锚点 %d, 工作流 %d, 模板 %d, 跳过 %d",
            report.imported_anchors,
            report.imported_workflows,
            report.imported_templates,
            len(report.skipped),
        )
        return report

    def _import_anchors(self, source: Path, report: MigrationReport) -> None:
        """导入旧锚点配置。"""

        paths = list((source / "anchors").glob("*/anchors.yaml"))
        paths.extend((source / "instruments").glob("*/instrument_profile.yaml"))
        seen: set[str] = set()
        for path in sorted(paths):
            legacy_id = self._legacy_profile_id(path)
            if legacy_id and legacy_id in seen:
                continue
            try:
                profile = self._load_anchor_profile(path)
            except Exception as exc:  # noqa: BLE001
                self._skip(report, path, exc)
                continue
            if profile.profile_id in seen:
                continue
            dump_yaml_contract(
                profile,
                self._workspace_dir / "anchors" / profile.profile_id / "anchors.yaml",
            )
            seen.add(profile.profile_id)
            report.imported_anchors += 1
        if report.imported_anchors:
            self._logger.info("已导入 %d 个旧锚点配置", report.imported_anchors)

    def _load_anchor_profile(self, path: Path) -> AnchorsContract:
        """加载并兼容旧锚点配置字段。"""

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            if "profile_id" not in raw and raw.get("device_id"):
                raw["profile_id"] = raw["device_id"]
            raw.pop("device_id", None)
            raw.pop("actions", None)
        return AnchorsContract.model_validate(raw)

    @staticmethod
    def _legacy_profile_id(path: Path) -> str | None:
        """从旧锚点文件中快速提取 profile ID。"""

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError:
            return None
        if not isinstance(raw, dict):
            return None
        profile_id = raw.get("profile_id") or raw.get("device_id")
        return str(profile_id) if profile_id else None

    def _import_workflows(self, source: Path, report: MigrationReport) -> None:
        """导入旧工作流草稿。"""

        for path in sorted((source / "workflows").glob("*/draft.yaml")):
            try:
                workflow = load_yaml_contract(path, WorkflowContract)
            except Exception as exc:  # noqa: BLE001
                self._skip(report, path, exc)
                continue
            dump_yaml_contract(
                workflow,
                (
                    self._workspace_dir
                    / "workflows"
                    / workflow.metadata.workflow_id
                    / "draft.yaml"
                ),
            )
            report.imported_workflows += 1
        if report.imported_workflows:
            self._logger.info("已导入 %d 个旧工作流", report.imported_workflows)

    def _import_templates(self, source: Path, report: MigrationReport) -> None:
        """导入旧本地模板工作流。"""

        for path in sorted((source / "templates").glob("*/*/workflow.yaml")):
            try:
                workflow = load_yaml_contract(path, WorkflowContract)
            except Exception as exc:  # noqa: BLE001
                self._skip(report, path, exc)
                continue
            template_id = workflow.metadata.template_id
            template_version = workflow.metadata.template_version
            if not template_id or not template_version:
                report.skipped.append(f"{path}: 缺少模板 ID 或版本")
                continue
            dump_yaml_contract(
                workflow,
                (
                    self._workspace_dir
                    / "templates"
                    / template_id
                    / template_version
                    / "workflow.yaml"
                ),
            )
            report.imported_templates += 1
        if report.imported_templates:
            self._logger.info("已导入 %d 个旧模板", report.imported_templates)

    def _skip(self, report: MigrationReport, path: Path, exc: Exception) -> None:
        """记录跳过的旧数据文件。"""

        detail = f"{path}: {exc}"
        report.skipped.append(detail)
        self._logger.warning("旧工作区导入跳过: %s", detail)
