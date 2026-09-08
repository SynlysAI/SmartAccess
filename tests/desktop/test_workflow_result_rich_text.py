from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_workflow_result_renders_markdown_headings_as_rich_text(tmp_path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    page = WorkflowPage(build_runtime_facade(AppSettings(workspace_dir=tmp_path)))
    page._set_result("## 步骤编排\n\n- step_1: 单击\n\n正文说明")

    plain = page._result.toPlainText()
    html = page._result.toHtml()

    assert "步骤编排" in plain
    assert "正文说明" in plain
    assert "步骤编排" in html
    assert "正文说明" in html
    assert "font-weight" in html or "<h" in html


def test_workflow_result_wraps_plain_text_with_default_title(tmp_path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    page = WorkflowPage(build_runtime_facade(AppSettings(workspace_dir=tmp_path)))
    page._set_result("标准化检查通过")

    html = page._result.toHtml()

    assert "检查结果" in html
    assert "标准化检查通过" in html
