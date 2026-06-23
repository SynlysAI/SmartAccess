"""SmartAccess 远程任务 worker 测试。"""

from smartaccess.runtime.application.remote_task_worker import RemoteTaskWorker


class FakeFacade:
    """测试 RuntimeFacade。"""

    def __init__(self) -> None:
        """初始化门面。"""
        self.started = []

    def start_run(self, workflow, *, background: bool = True):
        """记录启动运行请求。"""
        self.started.append((workflow, background))
        return type("Session", (), {"session_id": "run_local_1"})()


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
            "device_id": "weixin",
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
            "device_id": "other",
            "workflow": {"metadata": {"workflow_id": "wf_other"}, "steps": []},
        }
    )

    assert result == "rejected"
    assert not facade.started
    assert uploader.events[0]["status"] == "rejected"
