from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_builds_and_navigates(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.shell.main_window import MainWindow

    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path), seed_demo=True)
    window = MainWindow(facade)

    assert window._stack.count() == 5
    for row in range(5):
        window._nav.setCurrentRow(row)
        assert window._stack.currentIndex() == row


def test_monitoring_events_reach_view_model(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.viewmodels.base import EventRelay
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path), seed_demo=True)
    relay = EventRelay(facade)
    vm = MonitoringViewModel(facade, relay)
    logs: list[str] = []
    vm.log_line.connect(logs.append)

    workflow = facade.list_workflows()[0]
    facade.start_run(workflow=workflow)  # synchronous: same-thread signals fire directly

    assert logs  # runtime events were relayed to the view model
