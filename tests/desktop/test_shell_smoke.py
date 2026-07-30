"""SmartAccess 桌面主壳和核心页面烟测。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.pages.template_page import TemplatePage  # noqa: E402
from smartaccess.desktop.shell.main_window import MainWindow  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402
from smartaccess.shared.contracts.workflow import (  # noqa: E402
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)

_APP: QApplication | None = None
DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


def _app() -> QApplication:
    """返回测试用 QApplication。

    Returns:
        QApplication 实例。
    """

    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _anchor(anchor_id: str) -> dict:
    """构造测试锚点。

    Args:
        anchor_id: 锚点 ID。

    Returns:
        锚点原始字典。
    """

    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 10, "y": 10, "width": 80, "height": 32},
            "normalized": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
        },
        "supported_actions": ["click"],
    }


def _facade(tmp_path: Path):
    """构造带基础锚点和工作流的运行时门面。

    Args:
        tmp_path: 测试工作区。

    Returns:
        RuntimeFacade 实例。
    """

    facade = build_runtime_facade(
        AppSettings(workspace_dir=tmp_path, device_id="pc-workstation")
    )
    facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="ElectroChem Console",
        capture_width=1322,
        capture_height=914,
        anchors=[_anchor("status_button")],
    )
    facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_test",
                author="test",
                anchor_profile=DEVICE_ID,
                lifecycle_state="Draft",
                template_id="tpl_test",
                template_version="1.0.0",
            ),
            steps=[
                WorkflowStep(
                    id="start_and_wait",
                    action="click",
                    anchor_id="status_button",
                    wait_seconds=1.0,
                )
            ],
        )
    )
    return facade


def test_main_window_builds_current_navigation_and_status(tmp_path: Path) -> None:
    """验证主窗口导航和右侧状态使用当前页面结构。"""

    _app()
    facade = _facade(tmp_path)
    window = MainWindow(facade.settings(), facade)

    labels = [window._nav.item(index).text() for index in range(window._nav.count())]

    assert window._stack.count() == 5
    assert labels == [
        "设备接入与校准",
        "工作流设计",
        "运行监控",
        "模板/平台",
        "运行概览",
    ]
    assert "执行端: pc-workstation" in window._context.text()
    for row in range(window._stack.count()):
        window._nav.setCurrentRow(row)
        assert window._stack.currentIndex() == row


def test_template_page_table_includes_workflow_column(tmp_path: Path) -> None:
    """验证模板/平台页表格展示工作流列。"""

    _app()
    facade = _facade(tmp_path)
    workflow = facade.get_workflow("wf_test")
    assert workflow is not None
    facade.publish_template(workflow)
    page = TemplatePage(facade)
    page.on_show()

    headers = [
        page._table.horizontalHeaderItem(index).text()
        for index in range(page._table.columnCount())
    ]

    assert "工作流" in headers
    workflow_column = headers.index("工作流")
    values = [
        page._table.item(row, workflow_column).text()
        for row in range(page._table.rowCount())
        if page._table.item(row, workflow_column) is not None
    ]
    assert "wf_test" in values
