"""SmartAccess 远程任务 worker 测试。"""

from smartaccess.shared.events.runtime import RuntimeEventName
from smartaccess.runtime.application.remote_task_worker import RemoteTaskWorker


class FakeFacade:
    """测试 RuntimeFacade。"""

    def __init__(self) -> None:
        """初始化门面。"""
        self.started = []
        self._subscriber = None

    def start_run(self, workflow, *, background: bool = True):
        """记录启动运行请求。"""
        self.started.append((workflow, background))
        return type("Session", (), {"session_id": "run_local_1"})()

    def subscribe(self, callback):
        """记录事件订阅。"""
        self._subscriber = callback
        return lambda: None


class FakeUploader:
    """测试事件上传器。"""

    def __init__(self) -> None:
        """初始化上传器。"""
        self.events = []

    def upload_event(
        self,
        run_id: str,
        event_type: str,
        status: str,
        payload: dict,
    ) -> None:
        """记录上传事件。"""
        self.events.append(
            {
                "run_id": run_id,
                "event_type": event_type,
                "status": status,
                "payload": payload,
            }
        )


def _make_event(name, session_id, **payload):
    """构造 RuntimeEvent 测试辅助函数。"""
    from smartaccess.shared.events.bus import RuntimeEvent
    return RuntimeEvent(name=name, session_id=session_id, payload=payload)


def test_worker_starts_matching_device_workflow() -> None:
    """验证 worker 消费匹配设备任务并启动本地 workflow。"""
    facade = FakeFacade()
    uploader = FakeUploader()
    worker = RemoteTaskWorker(
        device_id="weixin",
        facade=facade,
        uploader=uploader,
    )

    result = worker.handle_message(
        {
            "run_id": "sa_run_1",
            "smartaccess_node_id": "weixin",
            "workflow": {
                "metadata": {
                    "workflow_id": "wf_weixin",
                    "anchor_profile": "weixin",
                },
                "steps": [{"id": "open", "anchor_id": "open", "action": "click"}],
            },
        }
    )

    assert result == "accepted"
    assert facade.started[0][0].metadata.workflow_id == "wf_weixin"
    assert uploader.events[0]["status"] == "accepted"


def test_worker_rejects_other_device_task() -> None:
    """验证 worker 拒绝其他设备任务。"""
    facade = FakeFacade()
    uploader = FakeUploader()
    worker = RemoteTaskWorker(
        device_id="weixin",
        facade=facade,
        uploader=uploader,
    )

    result = worker.handle_message(
        {
            "run_id": "sa_run_2",
            "smartaccess_node_id": "other",
            "workflow": {"metadata": {"workflow_id": "wf_other"}, "steps": []},
        }
    )

    assert result == "rejected"
    assert not facade.started
    assert uploader.events[0]["status"] == "rejected"


def test_event_subscription_forwards_step_events() -> None:
    """验证 worker 将本地运行时事件转换为平台事件上传。"""
    facade = FakeFacade()
    uploader = FakeUploader()
    worker = RemoteTaskWorker(
        device_id="weixin",
        facade=facade,
        uploader=uploader,
    )

    worker.handle_message(
        {
            "run_id": "sa_run_3",
            "smartaccess_node_id": "weixin",
            "workflow": {
                "metadata": {
                    "workflow_id": "wf_weixin",
                    "anchor_profile": "weixin",
                },
                "steps": [
                    {"id": "open", "anchor_id": "open", "action": "click"},
                    {"id": "observe", "anchor_id": "status", "action": "observe"},
                ],
            },
        }
    )

    uploader.events.clear()
    facade._subscriber(
        _make_event(
            RuntimeEventName.RUN_STARTED,
            "run_local_1",
            workflow_id="wf_weixin",
        )
    )
    assert uploader.events[0]["status"] == "running"
    assert uploader.events[0]["event_type"] == "run.started"

    uploader.events.clear()
    facade._subscriber(
        _make_event(
            RuntimeEventName.RUN_STEP_SUCCEEDED,
            "run_local_1",
            step_id="open",
            workflow_id="wf_weixin",
        )
    )
    assert uploader.events[0]["event_type"] == "step.completed"
    assert uploader.events[0]["payload"]["step_id"] == "open"
    assert uploader.events[0]["payload"]["step_index"] == 0

    uploader.events.clear()
    facade._subscriber(
        _make_event(
            RuntimeEventName.RUN_COMPLETED,
            "run_local_1",
            workflow_id="wf_weixin",
        )
    )
    assert uploader.events[0]["status"] == "success"
    assert uploader.events[0]["event_type"] == "run.completed"


def test_event_ignores_unmapped_session() -> None:
    """验证 worker 忽略未映射 session 的事件。"""
    facade = FakeFacade()
    uploader = FakeUploader()
    RemoteTaskWorker(
        device_id="weixin",
        facade=facade,
        uploader=uploader,
    )

    facade._subscriber(
        _make_event(
            RuntimeEventName.RUN_STARTED,
            "unknown_session",
            workflow_id="wf_other",
        )
    )
    assert len(uploader.events) == 0
