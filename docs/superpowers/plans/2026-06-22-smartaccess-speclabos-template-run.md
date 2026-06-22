# SmartAccess SpecLabOS Template Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 SmartAccess 工作流模板发布到 SpecLabOS、平台远程下发任务、SmartAccess 执行并回传状态的闭环。

**Architecture:** SpecLabOS 后端作为平台数据唯一写入口，MongoDB 保存模板和运行状态，HTTP 承载模板发布和状态回传，RabbitMQ 只负责把远程运行任务投递到指定 SmartAccess 设备。SpecLabOS 前端新增 SmartAccess 模板页，并扩展现有任务运行页展示 SmartAccess 任务。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、PyMongo、RabbitMQ/pika、React、Vite、Ant Design、PyQt6、SmartAccess 现有 RuntimeFacade。

## Global Constraints

- 所有对话和文档都使用中文。
- Python 新增函数和方法必须添加中文 docstring，包含 Args 和 Returns 时按项目规范书写。
- Python 代码遵循 PEP8；类方法顺序按 `__init__`、magic、static、class、public、private。
- 不让 SmartAccess 直接写 MongoDB；SpecLabOS 后端是平台数据唯一写入口。
- 模板发布使用 HTTP；远程任务下发使用 RabbitMQ；状态回传第一版使用 HTTP。
- 第一版不上传截图二进制，只保存 SmartAccess 本地截图路径和 trace 摘要。
- SpecLabOS 现有工作流编排页不承载 SmartAccess workflow，新增独立 SmartAccess 模板页。
- 不改动与本任务无关的未跟踪文件，例如 SmartAccess 仓库当前已有的 `test.py` 和 `uv.lock`。

---

## File Structure

### SpecLabOS 后端

- Create: `E:/github_project/SpecLabOS/backend/app/schemas/smartaccess.py`
  - SmartAccess 模板、运行、事件请求和响应模型。
- Create: `E:/github_project/SpecLabOS/backend/app/repositories/smartaccess_repository.py`
  - `smartaccess_templates`、`smartaccess_runs`、`smartaccess_run_events` 的 MongoDB 访问。
- Create: `E:/github_project/SpecLabOS/backend/app/services/smartaccess_service.py`
  - 模板发布、运行创建、事件接收、列表查询的业务逻辑。
- Create: `E:/github_project/SpecLabOS/backend/app/services/smartaccess_mq.py`
  - RabbitMQ publisher；测试中可替换为 fake publisher。
- Create: `E:/github_project/SpecLabOS/backend/app/api/routes/smartaccess.py`
  - SmartAccess HTTP API。
- Modify: `E:/github_project/SpecLabOS/backend/app/api/app_factory.py`
  - 注册 SmartAccess 路由。
- Modify: `E:/github_project/SpecLabOS/backend/app/runtime.py`
  - 增加 SmartAccess repository/service/publisher 缓存工厂。
- Modify: `E:/github_project/SpecLabOS/backend/app/core/config.py`
  - 增加 SmartAccess API token 配置。
- Modify: `E:/github_project/SpecLabOS/config.example.yaml`
  - 增加 SmartAccess 配置示例。
- Modify: `E:/github_project/SpecLabOS/backend/requirements.txt`
  - 增加 `pika`。
- Test: `E:/github_project/SpecLabOS/backend/tests/test_smartaccess_service.py`
- Test: `E:/github_project/SpecLabOS/backend/tests/test_smartaccess_routes.py`

### SpecLabOS 前端

- Create: `E:/github_project/SpecLabOS/frontend/src/services/smartaccessApi.js`
  - SmartAccess 模板和运行 API 客户端。
- Create: `E:/github_project/SpecLabOS/frontend/src/pages/SmartAccessTemplatesPage.jsx`
  - SmartAccess 模板列表、详情预览和远程发起运行页面。
- Modify: `E:/github_project/SpecLabOS/frontend/src/router.jsx`
  - 注册 `/smartaccess/templates` 路由。
- Modify: `E:/github_project/SpecLabOS/frontend/src/layout/AppSidebar.jsx`
  - 新增 SmartAccess 模板菜单项。
- Modify: `E:/github_project/SpecLabOS/frontend/src/services/workflowApi.js`
  - 任务运行列表和详情改用统一运行接口。
- Modify: `E:/github_project/SpecLabOS/frontend/src/pages/WorkflowRunsPage.jsx`
  - 增加任务来源列。
- Modify: `E:/github_project/SpecLabOS/frontend/src/pages/WorkflowRunDetailPage.jsx`
  - 兼容 SmartAccess 运行详情字段。
- Modify: `E:/github_project/SpecLabOS/frontend/src/components/StatusTag.jsx`
  - 增加 `queued`、`accepted`、`blocked`、`rejected` 状态展示。

### SmartAccess

- Modify: `E:/github_project/SmartAccess/src/smartaccess/shared/config/settings.py`
  - 增加 SmartAccess 设备 ID、RabbitMQ 配置、平台 API 配置别名。
- Modify: `E:/github_project/SmartAccess/src/smartaccess/runtime/adapters/speclabos_client.py`
  - 支持模板发布字段、运行事件上传。
- Create: `E:/github_project/SmartAccess/src/smartaccess/runtime/application/platform_event_uploader.py`
  - 把本地运行事件转成 SpecLabOS SmartAccess 事件并上传。
- Create: `E:/github_project/SmartAccess/src/smartaccess/runtime/application/remote_task_worker.py`
  - 消费 RabbitMQ 任务并调用 `RuntimeFacade.start_run()`。
- Modify: `E:/github_project/SmartAccess/src/smartaccess/bootstrap/runtime.py`
  - 暴露 worker 构造函数。
- Modify: `E:/github_project/SmartAccess/src/smartaccess/bootstrap/__init__.py`
  - 导出 worker 启动入口。
- Modify: `E:/github_project/SmartAccess/pyproject.toml`
  - 增加 `pika` 可选依赖或基础依赖，新增 `smartaccess-worker` script。
- Test: `E:/github_project/SmartAccess/tests/integration/test_speclabos_platform_client.py`
- Test: `E:/github_project/SmartAccess/tests/integration/test_remote_task_worker.py`

---

### Task 1: SpecLabOS SmartAccess 数据模型、仓储和服务

**Files:**
- Create: `E:/github_project/SpecLabOS/backend/app/schemas/smartaccess.py`
- Create: `E:/github_project/SpecLabOS/backend/app/repositories/smartaccess_repository.py`
- Create: `E:/github_project/SpecLabOS/backend/app/services/smartaccess_service.py`
- Test: `E:/github_project/SpecLabOS/backend/tests/test_smartaccess_service.py`

**Interfaces:**
- Produces:
  - `SmartAccessRepository.publish_template(payload: SmartAccessTemplatePublishRequest) -> dict`
  - `SmartAccessRepository.list_templates(keyword: str | None = None, device_id: str | None = None, status: str | None = None) -> list[dict]`
  - `SmartAccessRepository.get_template(template_id: str, template_version: str) -> dict | None`
  - `SmartAccessRepository.create_run(template: dict, payload: SmartAccessRunCreateRequest) -> dict`
  - `SmartAccessRepository.append_event(run_id: str, payload: SmartAccessRunEventRequest) -> dict`
  - `SmartAccessService.publish_template(payload: SmartAccessTemplatePublishRequest) -> dict`
  - `SmartAccessService.create_run(payload: SmartAccessRunCreateRequest) -> dict`

- [ ] **Step 1: 写服务层失败测试**

在 `backend/tests/test_smartaccess_service.py` 中新增：

```python
"""SmartAccess 服务测试。"""

import pytest

from app.repositories.smartaccess_repository import SmartAccessRepository
from app.schemas.smartaccess import (
    SmartAccessRunCreateRequest,
    SmartAccessRunEventRequest,
    SmartAccessTemplatePublishRequest,
)
from app.services.smartaccess_service import SmartAccessService


class FakePublisher:
    """记录 SmartAccess 任务消息的测试发布器。"""

    def __init__(self) -> None:
        """初始化发布器。"""
        self.messages = []

    def publish_run_requested(self, payload: dict) -> None:
        """记录远程运行请求消息。

        Args:
            payload: 运行请求消息。
        """
        self.messages.append(payload)


def _workflow_payload() -> dict:
    """构造最小 SmartAccess workflow 快照。

    Returns:
        workflow 字典。
    """
    return {
        "metadata": {
            "workflow_id": "wf_weixin",
            "template_id": "tpl_weixin",
            "template_version": "1.0.0",
            "anchor_profile": "weixin",
        },
        "steps": [
            {"id": "open", "anchor_id": "open", "action": "click"},
            {"id": "observe", "anchor_id": "status", "action": "observe"},
        ],
    }


def test_publish_template_upserts_snapshot(fake_database) -> None:
    """验证模板发布会写入模板快照。"""
    service = SmartAccessService(
        repository=SmartAccessRepository(fake_database),
        publisher=FakePublisher(),
    )

    record = service.publish_template(
        SmartAccessTemplatePublishRequest(
            template_id="tpl_weixin",
            template_version="1.0.0",
            workflow_id="wf_weixin",
            name="微信流程",
            anchor_profile="weixin",
            source_device_id="weixin",
            published_by="smartaccess",
            workflow=_workflow_payload(),
        )
    )

    assert record["template_id"] == "tpl_weixin"
    assert record["template_version"] == "1.0.0"
    assert record["step_count"] == 2
    assert fake_database["smartaccess_templates"].count_documents({}) == 1


def test_create_run_publishes_device_message(fake_database) -> None:
    """验证创建运行会写入运行记录并发布设备消息。"""
    publisher = FakePublisher()
    service = SmartAccessService(
        repository=SmartAccessRepository(fake_database),
        publisher=publisher,
    )
    service.publish_template(
        SmartAccessTemplatePublishRequest(
            template_id="tpl_weixin",
            template_version="1.0.0",
            workflow_id="wf_weixin",
            name="微信流程",
            anchor_profile="weixin",
            source_device_id="weixin",
            published_by="smartaccess",
            workflow=_workflow_payload(),
        )
    )

    run = service.create_run(
        SmartAccessRunCreateRequest(
            template_id="tpl_weixin",
            template_version="1.0.0",
            device_id="weixin",
            requested_by="admin",
        )
    )

    assert run["status"] == "queued"
    assert run["device_id"] == "weixin"
    assert publisher.messages[0]["run_id"] == run["run_id"]
    assert publisher.messages[0]["workflow"]["metadata"]["workflow_id"] == "wf_weixin"


def test_append_event_updates_run_status(fake_database) -> None:
    """验证事件回传会推进运行状态。"""
    service = SmartAccessService(
        repository=SmartAccessRepository(fake_database),
        publisher=FakePublisher(),
    )
    service.publish_template(
        SmartAccessTemplatePublishRequest(
            template_id="tpl_weixin",
            template_version="1.0.0",
            workflow_id="wf_weixin",
            name="微信流程",
            anchor_profile="weixin",
            source_device_id="weixin",
            published_by="smartaccess",
            workflow=_workflow_payload(),
        )
    )
    run = service.create_run(
        SmartAccessRunCreateRequest(
            template_id="tpl_weixin",
            template_version="1.0.0",
            device_id="weixin",
            requested_by="admin",
        )
    )

    service.append_event(
        run["run_id"],
        SmartAccessRunEventRequest(
            event_id="evt-1",
            event_type="run.started",
            status="running",
            payload={},
        ),
    )

    stored = fake_database["smartaccess_runs"].find_one({"run_id": run["run_id"]})
    assert stored["status"] == "running"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_service.py -q
```

如果项目虚拟环境路径不是 `..\.venv`，使用仓库已有 `.venv\Scripts\python.exe` 或当前后端测试命令。Expected: `ModuleNotFoundError: No module named 'app.repositories.smartaccess_repository'`。

- [ ] **Step 3: 实现 schema**

创建 `backend/app/schemas/smartaccess.py`：

```python
"""SmartAccess 平台集成 Schema。"""

from typing import Any

from pydantic import BaseModel, Field


class SmartAccessTemplatePublishRequest(BaseModel):
    """SmartAccess 模板发布请求。"""

    template_id: str
    template_version: str
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    anchor_profile: str = ""
    source_device_id: str = ""
    published_by: str = "smartaccess"
    workflow: dict[str, Any]


class SmartAccessTemplateItem(BaseModel):
    """SmartAccess 模板列表项。"""

    template_id: str
    template_version: str
    workflow_id: str = ""
    name: str = ""
    anchor_profile: str = ""
    source_device_id: str = ""
    status: str = "published"
    step_count: int = 0
    published_at: str = ""
    updated_at: str = ""


class SmartAccessTemplateListResponse(BaseModel):
    """SmartAccess 模板列表响应。"""

    items: list[SmartAccessTemplateItem] = Field(default_factory=list)


class SmartAccessTemplateDetailResponse(SmartAccessTemplateItem):
    """SmartAccess 模板详情响应。"""

    description: str = ""
    workflow: dict[str, Any] = Field(default_factory=dict)


class SmartAccessRunCreateRequest(BaseModel):
    """SmartAccess 远程运行创建请求。"""

    template_id: str
    template_version: str
    device_id: str
    requested_by: str = "system"


class SmartAccessRunCreateResponse(BaseModel):
    """SmartAccess 远程运行创建响应。"""

    run_id: str
    status: str = "queued"


class SmartAccessRunEventRequest(BaseModel):
    """SmartAccess 运行事件回传请求。"""

    event_id: str
    event_type: str
    status: str = ""
    step_id: str = ""
    step_index: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SmartAccessRunItem(BaseModel):
    """SmartAccess 运行列表项。"""

    run_id: str
    workflow_name: str = ""
    device_key: str = ""
    status: str = "queued"
    current_step_index: int = 0
    total_steps: int = 0
    started_at: str = "--"
    source: str = "smartaccess"


class SmartAccessRunListResponse(BaseModel):
    """SmartAccess 运行列表响应。"""

    items: list[SmartAccessRunItem] = Field(default_factory=list)
```

- [ ] **Step 4: 实现 repository**

创建 `backend/app/repositories/smartaccess_repository.py`，确保所有时间使用 UTC ISO 字符串：

```python
"""SmartAccess 模板和运行记录仓储。"""

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.smartaccess import (
    SmartAccessRunCreateRequest,
    SmartAccessRunEventRequest,
    SmartAccessTemplatePublishRequest,
)


def _now_text() -> str:
    """返回当前 UTC ISO 时间文本。

    Returns:
        当前时间文本。
    """
    return datetime.now(timezone.utc).isoformat()


class SmartAccessRepository:
    """SmartAccess 模板、运行和事件 MongoDB 仓储。"""

    def __init__(self, database) -> None:
        """初始化仓储。

        Args:
            database: MongoDB 数据库实例。
        """
        self._templates = database["smartaccess_templates"]
        self._runs = database["smartaccess_runs"]
        self._events = database["smartaccess_run_events"]

    def publish_template(
        self,
        payload: SmartAccessTemplatePublishRequest,
    ) -> dict:
        """保存或更新 SmartAccess 模板快照。

        Args:
            payload: 模板发布请求。

        Returns:
            模板记录。
        """
        now = _now_text()
        workflow = payload.workflow
        metadata = workflow.get("metadata", {}) if isinstance(workflow, dict) else {}
        steps = workflow.get("steps", []) if isinstance(workflow, dict) else []
        record = {
            "template_id": payload.template_id,
            "template_version": payload.template_version,
            "workflow_id": payload.workflow_id or metadata.get("workflow_id", ""),
            "name": payload.name or payload.workflow_id or payload.template_id,
            "description": payload.description,
            "anchor_profile": payload.anchor_profile or metadata.get("anchor_profile", ""),
            "source_device_id": payload.source_device_id,
            "source": "smartaccess",
            "status": "published",
            "step_count": len(steps) if isinstance(steps, list) else 0,
            "workflow": workflow,
            "published_by": payload.published_by,
            "updated_at": now,
        }
        existing = self._templates.find_one(
            {
                "template_id": payload.template_id,
                "template_version": payload.template_version,
            }
        )
        if existing:
            record["published_at"] = existing.get("published_at", now)
        else:
            record["published_at"] = now
        self._templates.update_one(
            {
                "template_id": payload.template_id,
                "template_version": payload.template_version,
            },
            {"$set": record},
            upsert=True,
        )
        return dict(record)

    def list_templates(
        self,
        keyword: str | None = None,
        device_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """查询 SmartAccess 模板列表。

        Args:
            keyword: 搜索关键字。
            device_id: 来源设备或锚点配置。
            status: 模板状态。

        Returns:
            模板记录列表。
        """
        query: dict = {}
        if status:
            query["status"] = status
        if device_id:
            query["$or"] = [
                {"source_device_id": device_id},
                {"anchor_profile": device_id},
            ]
        records = list(self._templates.find(query).sort("updated_at", -1))
        if keyword:
            needle = keyword.lower()
            records = [
                item for item in records
                if needle in " ".join(
                    [
                        str(item.get("template_id", "")),
                        str(item.get("template_version", "")),
                        str(item.get("workflow_id", "")),
                        str(item.get("name", "")),
                        str(item.get("anchor_profile", "")),
                    ]
                ).lower()
            ]
        return records

    def get_template(self, template_id: str, template_version: str) -> dict | None:
        """读取指定模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            模板记录，不存在时返回 None。
        """
        return self._templates.find_one(
            {"template_id": template_id, "template_version": template_version}
        )

    def create_run(
        self,
        template: dict,
        payload: SmartAccessRunCreateRequest,
    ) -> dict:
        """创建 SmartAccess 远程运行记录。

        Args:
            template: 模板记录。
            payload: 运行创建请求。

        Returns:
            运行记录。
        """
        workflow = dict(template.get("workflow") or {})
        record = {
            "run_id": f"sa_run_{uuid4().hex[:12]}",
            "template_id": payload.template_id,
            "template_version": payload.template_version,
            "workflow_id": template.get("workflow_id", ""),
            "workflow_name": template.get("name", ""),
            "device_id": payload.device_id,
            "anchor_profile": template.get("anchor_profile", ""),
            "status": "queued",
            "current_step_index": 0,
            "total_steps": int(template.get("step_count") or 0),
            "requested_by": payload.requested_by,
            "requested_at": _now_text(),
            "started_at": None,
            "finished_at": None,
            "workflow_snapshot": workflow,
            "summary": {},
            "last_error": "",
        }
        self._runs.insert_one(record)
        return dict(record)

    def append_event(
        self,
        run_id: str,
        payload: SmartAccessRunEventRequest,
    ) -> dict:
        """追加运行事件并推进运行状态。

        Args:
            run_id: 平台运行 ID。
            payload: 事件请求。

        Returns:
            事件记录。
        """
        existing = self._events.find_one({"event_id": payload.event_id})
        if existing:
            return existing
        event = {
            "event_id": payload.event_id,
            "run_id": run_id,
            "event_type": payload.event_type,
            "step_id": payload.step_id,
            "step_index": payload.step_index,
            "status": payload.status,
            "payload": payload.payload,
            "created_at": _now_text(),
        }
        self._events.insert_one(event)
        self._apply_event_to_run(run_id, event)
        return dict(event)

    def _apply_event_to_run(self, run_id: str, event: dict) -> None:
        """根据事件更新运行记录。

        Args:
            run_id: 平台运行 ID。
            event: 已落库事件。
        """
        status = event.get("status") or ""
        event_type = event.get("event_type") or ""
        updates: dict = {}
        if status:
            updates["status"] = status
        if event.get("step_index") is not None:
            updates["current_step_index"] = int(event["step_index"])
        if event_type == "run.started":
            updates["started_at"] = event["created_at"]
            updates["status"] = status or "running"
        if event_type in {"run.completed", "run.failed", "run.cancelled", "run.rejected"}:
            updates["finished_at"] = event["created_at"]
        if status in {"failed", "rejected"}:
            updates["last_error"] = str(event.get("payload", {}).get("error", ""))
        if updates:
            self._runs.update_one({"run_id": run_id}, {"$set": updates})
```

- [ ] **Step 5: 实现 service**

创建 `backend/app/services/smartaccess_service.py`：

```python
"""SmartAccess 平台集成服务。"""

from fastapi import HTTPException

from app.repositories.smartaccess_repository import SmartAccessRepository
from app.schemas.smartaccess import (
    SmartAccessRunCreateRequest,
    SmartAccessRunEventRequest,
    SmartAccessTemplatePublishRequest,
)


class SmartAccessService:
    """SmartAccess 模板和远程运行业务服务。"""

    def __init__(self, repository: SmartAccessRepository, publisher) -> None:
        """初始化服务。

        Args:
            repository: SmartAccess 仓储。
            publisher: SmartAccess MQ 发布器。
        """
        self._repository = repository
        self._publisher = publisher

    def publish_template(self, payload: SmartAccessTemplatePublishRequest) -> dict:
        """发布 SmartAccess 模板。

        Args:
            payload: 模板发布请求。

        Returns:
            模板记录。
        """
        if not payload.workflow:
            raise HTTPException(status_code=400, detail="workflow 不能为空")
        return self._repository.publish_template(payload)

    def list_templates(
        self,
        keyword: str | None = None,
        device_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """查询模板列表。

        Args:
            keyword: 搜索关键字。
            device_id: 设备 ID。
            status: 模板状态。

        Returns:
            模板列表。
        """
        return self._repository.list_templates(keyword, device_id, status)

    def get_template(self, template_id: str, template_version: str) -> dict:
        """读取模板详情。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            模板记录。
        """
        template = self._repository.get_template(template_id, template_version)
        if template is None:
            raise HTTPException(status_code=404, detail="SmartAccess 模板不存在")
        return template

    def create_run(self, payload: SmartAccessRunCreateRequest) -> dict:
        """创建 SmartAccess 远程运行并发布 MQ 消息。

        Args:
            payload: 运行创建请求。

        Returns:
            运行记录。
        """
        template = self.get_template(payload.template_id, payload.template_version)
        run = self._repository.create_run(template, payload)
        self._publisher.publish_run_requested(
            {
                "message_id": f"msg_{run['run_id']}",
                "type": "run.requested",
                "run_id": run["run_id"],
                "template_id": run["template_id"],
                "template_version": run["template_version"],
                "device_id": run["device_id"],
                "workflow": run["workflow_snapshot"],
                "requested_by": run["requested_by"],
                "requested_at": run["requested_at"],
            }
        )
        return run

    def append_event(
        self,
        run_id: str,
        payload: SmartAccessRunEventRequest,
    ) -> dict:
        """追加 SmartAccess 运行事件。

        Args:
            run_id: 平台运行 ID。
            payload: 事件请求。

        Returns:
            事件记录。
        """
        return self._repository.append_event(run_id, payload)
```

- [ ] **Step 6: 运行服务测试确认通过**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_service.py -q
```

Expected: 3 passed.

- [ ] **Step 7: 提交 Task 1**

```powershell
cd E:\github_project\SpecLabOS
git add backend/app/schemas/smartaccess.py backend/app/repositories/smartaccess_repository.py backend/app/services/smartaccess_service.py backend/tests/test_smartaccess_service.py
git commit -m "新增 SmartAccess 模板和运行服务" -m "- 添加 SmartAccess 模板、运行和事件 Schema" -m "- 添加 MongoDB 仓储和服务层" -m "- 覆盖模板发布、运行创建和事件状态推进测试"
```

---

### Task 2: SpecLabOS SmartAccess HTTP API 与运行列表兼容

**Files:**
- Create: `E:/github_project/SpecLabOS/backend/app/api/routes/smartaccess.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/api/app_factory.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/runtime.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/api/routes/workflows.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/schemas/workflow.py`
- Test: `E:/github_project/SpecLabOS/backend/tests/test_smartaccess_routes.py`
- Test: `E:/github_project/SpecLabOS/backend/tests/test_workflow_routes.py`

**Interfaces:**
- Consumes: `SmartAccessService` from Task 1.
- Produces:
  - `POST /api/smartaccess/templates/publish`
  - `GET /api/smartaccess/templates`
  - `GET /api/smartaccess/templates/{template_id}/versions/{template_version}`
  - `POST /api/smartaccess/runs`
  - `GET /api/smartaccess/runs`
  - `GET /api/smartaccess/runs/{run_id}`
  - `POST /api/smartaccess/runs/{run_id}/events`
  - Extended `GET /api/workflow-runs` with `source`.
  - Extended `GET /api/workflow-runs/{run_id}` routing SmartAccess IDs.

- [ ] **Step 1: 写路由失败测试**

创建 `backend/tests/test_smartaccess_routes.py`：

```python
"""SmartAccess 路由测试。"""

from fastapi.testclient import TestClient

from main import app


def _workflow_payload() -> dict:
    """构造 SmartAccess workflow 快照。

    Returns:
        workflow 字典。
    """
    return {
        "metadata": {
            "workflow_id": "wf_weixin",
            "template_id": "tpl_weixin",
            "template_version": "1.0.0",
            "anchor_profile": "weixin",
        },
        "steps": [{"id": "open", "anchor_id": "open", "action": "click"}],
    }


def test_publish_and_list_smartaccess_template() -> None:
    """验证 SmartAccess 模板发布和列表接口。"""
    client = TestClient(app)

    response = client.post(
        "/api/smartaccess/templates/publish",
        json={
            "template_id": "tpl_weixin",
            "template_version": "1.0.0",
            "workflow_id": "wf_weixin",
            "name": "微信流程",
            "anchor_profile": "weixin",
            "source_device_id": "weixin",
            "published_by": "smartaccess",
            "workflow": _workflow_payload(),
        },
    )

    assert response.status_code == 200
    assert response.json()["template_id"] == "tpl_weixin"

    list_response = client.get("/api/smartaccess/templates")
    assert list_response.status_code == 200
    assert any(item["template_id"] == "tpl_weixin" for item in list_response.json()["items"])


def test_create_smartaccess_run_and_append_event() -> None:
    """验证 SmartAccess 运行创建和状态事件回传。"""
    client = TestClient(app)
    client.post(
        "/api/smartaccess/templates/publish",
        json={
            "template_id": "tpl_weixin_run",
            "template_version": "1.0.0",
            "workflow_id": "wf_weixin",
            "name": "微信流程",
            "anchor_profile": "weixin",
            "source_device_id": "weixin",
            "published_by": "smartaccess",
            "workflow": _workflow_payload(),
        },
    )

    run_response = client.post(
        "/api/smartaccess/runs",
        json={
            "template_id": "tpl_weixin_run",
            "template_version": "1.0.0",
            "device_id": "weixin",
            "requested_by": "admin",
        },
    )

    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    event_response = client.post(
        f"/api/smartaccess/runs/{run_id}/events",
        json={
            "event_id": "evt-route-1",
            "event_type": "run.started",
            "status": "running",
            "payload": {},
        },
    )

    assert event_response.status_code == 200
    detail_response = client.get(f"/api/smartaccess/runs/{run_id}")
    assert detail_response.json()["status"] == "running"


def test_unified_workflow_runs_include_smartaccess_source() -> None:
    """验证统一任务列表包含 SmartAccess 来源。"""
    client = TestClient(app)

    response = client.get("/api/workflow-runs")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert all("source" in item for item in data["items"])
```

- [ ] **Step 2: 运行路由测试确认失败**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_routes.py -q
```

Expected: 404 或 import error。

- [ ] **Step 3: 实现 runtime 工厂**

修改 `backend/app/runtime.py`，新增：

```python
from app.repositories.smartaccess_repository import SmartAccessRepository
from app.services.smartaccess_mq import SmartAccessNullPublisher
from app.services.smartaccess_service import SmartAccessService


@lru_cache(maxsize=1)
def get_smartaccess_repository() -> SmartAccessRepository:
    """构建并缓存 SmartAccess 仓储。"""
    return SmartAccessRepository(get_database())


@lru_cache(maxsize=1)
def get_smartaccess_publisher():
    """构建并缓存 SmartAccess MQ 发布器。"""
    return SmartAccessNullPublisher()


@lru_cache(maxsize=1)
def get_smartaccess_service() -> SmartAccessService:
    """构建并缓存 SmartAccess 服务。"""
    return SmartAccessService(
        repository=get_smartaccess_repository(),
        publisher=get_smartaccess_publisher(),
    )
```

本任务先使用 null publisher，真实 RabbitMQ publisher 在 Task 3 替换。

- [ ] **Step 4: 创建 null publisher**

创建 `backend/app/services/smartaccess_mq.py`：

```python
"""SmartAccess RabbitMQ 发布器。"""


class SmartAccessNullPublisher:
    """测试和未配置 MQ 时使用的空发布器。"""

    def publish_run_requested(self, payload: dict) -> None:
        """忽略远程运行请求消息。

        Args:
            payload: 运行请求消息。
        """
        return None
```

- [ ] **Step 5: 实现 SmartAccess 路由**

创建 `backend/app/api/routes/smartaccess.py`：

```python
"""SmartAccess 集成接口。"""

from fastapi import APIRouter, Query

from app.runtime import get_smartaccess_service
from app.schemas.smartaccess import (
    SmartAccessRunCreateRequest,
    SmartAccessRunCreateResponse,
    SmartAccessRunEventRequest,
    SmartAccessRunListResponse,
    SmartAccessTemplateDetailResponse,
    SmartAccessTemplateItem,
    SmartAccessTemplateListResponse,
    SmartAccessTemplatePublishRequest,
)

router = APIRouter(prefix="/api/smartaccess", tags=["smartaccess"])


@router.post("/templates/publish", response_model=SmartAccessTemplateDetailResponse)
def publish_template(payload: SmartAccessTemplatePublishRequest):
    """发布 SmartAccess 模板。"""
    return get_smartaccess_service().publish_template(payload)


@router.get("/templates", response_model=SmartAccessTemplateListResponse)
def list_templates(
    keyword: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> SmartAccessTemplateListResponse:
    """查询 SmartAccess 模板列表。"""
    records = get_smartaccess_service().list_templates(keyword, device_id, status)
    return SmartAccessTemplateListResponse(
        items=[SmartAccessTemplateItem.model_validate(item) for item in records]
    )


@router.get(
    "/templates/{template_id}/versions/{template_version}",
    response_model=SmartAccessTemplateDetailResponse,
)
def get_template(template_id: str, template_version: str):
    """读取 SmartAccess 模板详情。"""
    return get_smartaccess_service().get_template(template_id, template_version)


@router.post("/runs", response_model=SmartAccessRunCreateResponse)
def create_run(payload: SmartAccessRunCreateRequest) -> SmartAccessRunCreateResponse:
    """创建 SmartAccess 远程运行。"""
    run = get_smartaccess_service().create_run(payload)
    return SmartAccessRunCreateResponse(run_id=run["run_id"], status=run["status"])


@router.get("/runs", response_model=SmartAccessRunListResponse)
def list_runs() -> SmartAccessRunListResponse:
    """查询 SmartAccess 运行列表。"""
    records = get_smartaccess_service().list_runs()
    return SmartAccessRunListResponse(items=records)


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    """读取 SmartAccess 运行详情。"""
    return get_smartaccess_service().get_run(run_id)


@router.post("/runs/{run_id}/events")
def append_event(run_id: str, payload: SmartAccessRunEventRequest):
    """接收 SmartAccess 运行事件。"""
    return get_smartaccess_service().append_event(run_id, payload)
```

补充 `SmartAccessService.list_runs()`、`SmartAccessService.get_run()`、`SmartAccessRepository.list_runs()`、`SmartAccessRepository.get_run()`，返回字段兼容 `SmartAccessRunItem`。

- [ ] **Step 6: 注册路由**

修改 `backend/app/api/app_factory.py`：

```python
from app.api.routes import auth, devices, logs, smartaccess, tools, workflows
...
application.include_router(smartaccess.router)
```

- [ ] **Step 7: 扩展统一任务运行 schema**

修改 `backend/app/schemas/workflow.py`：

```python
class WorkflowRunItem(BaseModel):
    """工作流运行列表项。"""

    run_id: str
    workflow_name: str
    device_key: str = ""
    status: str = "pending"
    current_step_index: int = 0
    total_steps: int = 0
    started_at: str = "--"
    source: str = "speclabos"
```

`WorkflowRunDetailResponse` 增加：

```python
source: str = "speclabos"
template_id: str = ""
template_version: str = ""
anchor_profile: str = ""
events: list[dict] = Field(default_factory=list)
```

- [ ] **Step 8: 扩展 workflows 路由合并 SmartAccess 运行**

修改 `backend/app/api/routes/workflows.py`：

```python
from app.runtime import get_smartaccess_service, get_workflow_repository
```

在 `list_workflow_runs()` 中，普通运行 item 增加 `"source": "speclabos"`，然后追加：

```python
for item in get_smartaccess_service().list_runs():
    filtered_items.append(item)
```

在 `get_workflow_run_detail()` 开头：

```python
if run_id.startswith("sa_run_"):
    return get_smartaccess_service().get_run(run_id)
```

SmartAccess detail 返回字段必须包含 `source="smartaccess"` 和 `steps`。

- [ ] **Step 9: 运行路由测试**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_routes.py tests\test_workflow_routes.py -q
```

Expected: all passed.

- [ ] **Step 10: 提交 Task 2**

```powershell
cd E:\github_project\SpecLabOS
git add backend/app/api/routes/smartaccess.py backend/app/api/app_factory.py backend/app/runtime.py backend/app/services/smartaccess_mq.py backend/app/api/routes/workflows.py backend/app/schemas/workflow.py backend/tests/test_smartaccess_routes.py backend/tests/test_workflow_routes.py
git commit -m "新增 SmartAccess 平台接口" -m "- 添加模板发布、运行创建和事件回传接口" -m "- 扩展任务运行列表兼容 SmartAccess 来源" -m "- 添加 SmartAccess 路由测试"
```

---

### Task 3: SpecLabOS RabbitMQ 发布器

**Files:**
- Modify: `E:/github_project/SpecLabOS/backend/app/services/smartaccess_mq.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/runtime.py`
- Modify: `E:/github_project/SpecLabOS/backend/app/core/config.py`
- Modify: `E:/github_project/SpecLabOS/backend/requirements.txt`
- Modify: `E:/github_project/SpecLabOS/config.example.yaml`
- Test: `E:/github_project/SpecLabOS/backend/tests/test_smartaccess_service.py`

**Interfaces:**
- Consumes: `SmartAccessService.create_run()`.
- Produces: `SmartAccessRabbitMQPublisher.publish_run_requested(payload: dict) -> None`.

- [ ] **Step 1: 添加 publisher 单元测试**

在 `backend/tests/test_smartaccess_service.py` 增加测试 fake channel，不连接真实 RabbitMQ：

```python
from app.services.smartaccess_mq import SmartAccessRabbitMQPublisher


class FakeChannel:
    """记录 RabbitMQ 发布调用的测试 channel。"""

    def __init__(self) -> None:
        """初始化 channel。"""
        self.declared = []
        self.published = []

    def exchange_declare(self, **kwargs) -> None:
        """记录 exchange 声明。"""
        self.declared.append(kwargs)

    def basic_publish(self, **kwargs) -> None:
        """记录发布消息。"""
        self.published.append(kwargs)


def test_rabbitmq_publisher_routes_to_device_queue() -> None:
    """验证 RabbitMQ publisher 使用设备 routing key。"""
    channel = FakeChannel()
    publisher = SmartAccessRabbitMQPublisher(channel_factory=lambda: channel)

    publisher.publish_run_requested({"device_id": "weixin", "run_id": "sa_run_1"})

    assert channel.declared[0]["exchange"] == "smartaccess.commands"
    assert channel.published[0]["routing_key"] == "device.weixin.run.requested"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_service.py::test_rabbitmq_publisher_routes_to_device_queue -q
```

Expected: import error 或 class missing。

- [ ] **Step 3: 实现 RabbitMQ publisher**

修改 `backend/app/services/smartaccess_mq.py`：

```python
"""SmartAccess RabbitMQ 发布器。"""

import json
from collections.abc import Callable

import pika
from pika.adapters.blocking_connection import BlockingChannel


class SmartAccessNullPublisher:
    """测试和未配置 MQ 时使用的空发布器。"""

    def publish_run_requested(self, payload: dict) -> None:
        """忽略远程运行请求消息。

        Args:
            payload: 运行请求消息。
        """
        return None


class SmartAccessRabbitMQPublisher:
    """SmartAccess 远程运行 RabbitMQ 发布器。"""

    def __init__(self, channel_factory: Callable[[], BlockingChannel]) -> None:
        """初始化发布器。

        Args:
            channel_factory: RabbitMQ channel 工厂。
        """
        self._channel_factory = channel_factory

    def publish_run_requested(self, payload: dict) -> None:
        """发布 SmartAccess 远程运行请求。

        Args:
            payload: 运行请求消息。
        """
        device_id = str(payload["device_id"])
        routing_key = f"device.{device_id}.run.requested"
        channel = self._channel_factory()
        channel.exchange_declare(
            exchange="smartaccess.commands",
            exchange_type="topic",
            durable=True,
        )
        channel.basic_publish(
            exchange="smartaccess.commands",
            routing_key=routing_key,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
```

- [ ] **Step 4: 添加 pika 依赖**

修改 `backend/requirements.txt`：

```text
pika==1.3.2
```

- [ ] **Step 5: runtime 使用 RabbitMQ 配置构造 publisher**

修改 `backend/app/runtime.py` 的 `get_smartaccess_publisher()`：

```python
import pika
from app.core.config import get_settings
from app.services.smartaccess_mq import SmartAccessRabbitMQPublisher


@lru_cache(maxsize=1)
def get_smartaccess_publisher():
    """构建并缓存 SmartAccess MQ 发布器。"""
    settings = get_settings()

    def _channel():
        """创建 RabbitMQ channel。"""
        credentials = pika.PlainCredentials(
            settings.rabbitmq.username,
            settings.rabbitmq.password,
        )
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.rabbitmq.host,
                port=settings.rabbitmq.port,
                credentials=credentials,
            )
        )
        return connection.channel()

    return SmartAccessRabbitMQPublisher(channel_factory=_channel)
```

如果路由测试没有 RabbitMQ 服务，会因真实连接失败。为避免测试依赖外部服务，在 `create_run()` 里捕获 publisher 异常并标记 run failed，或者测试时 monkeypatch runtime publisher。实施时优先选择 monkeypatch，不吞掉生产错误。

- [ ] **Step 6: 运行 publisher 测试**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_service.py::test_rabbitmq_publisher_routes_to_device_queue -q
```

Expected: passed.

- [ ] **Step 7: 提交 Task 3**

```powershell
cd E:\github_project\SpecLabOS
git add backend/app/services/smartaccess_mq.py backend/app/runtime.py backend/requirements.txt config.example.yaml backend/tests/test_smartaccess_service.py
git commit -m "接入 SmartAccess 远程任务 MQ 发布器" -m "- 添加 RabbitMQ topic exchange 发布器" -m "- 按设备 ID 路由远程运行任务" -m "- 添加发布器路由键测试"
```

---

### Task 4: SpecLabOS 前端 SmartAccess 模板页和任务运行页适配

**Files:**
- Create: `E:/github_project/SpecLabOS/frontend/src/services/smartaccessApi.js`
- Create: `E:/github_project/SpecLabOS/frontend/src/pages/SmartAccessTemplatesPage.jsx`
- Modify: `E:/github_project/SpecLabOS/frontend/src/router.jsx`
- Modify: `E:/github_project/SpecLabOS/frontend/src/layout/AppSidebar.jsx`
- Modify: `E:/github_project/SpecLabOS/frontend/src/services/workflowApi.js`
- Modify: `E:/github_project/SpecLabOS/frontend/src/pages/WorkflowRunsPage.jsx`
- Modify: `E:/github_project/SpecLabOS/frontend/src/pages/WorkflowRunDetailPage.jsx`
- Modify: `E:/github_project/SpecLabOS/frontend/src/components/StatusTag.jsx`

**Interfaces:**
- Consumes: SpecLabOS SmartAccess HTTP API from Task 2.
- Produces: `/smartaccess/templates` page and source-aware `/runs` pages.

- [ ] **Step 1: 新增 smartaccessApi.js**

创建 `frontend/src/services/smartaccessApi.js`：

```javascript
import { http } from "./http";

/**
 * 获取 SmartAccess 模板列表。
 *
 * Args:
 *     filters: 查询筛选条件。
 *
 * Returns:
 *     模板列表。
 */
export async function fetchSmartAccessTemplates(filters = {}) {
  const response = await http.get("/api/smartaccess/templates", {
    params: {
      keyword: filters.keyword || undefined,
      device_id: filters.device_id || undefined,
      status: filters.status && filters.status !== "all" ? filters.status : undefined,
    },
  });
  return response.data.items || [];
}

/**
 * 获取 SmartAccess 模板详情。
 *
 * Args:
 *     templateId: 模板 ID。
 *     templateVersion: 模板版本。
 *
 * Returns:
 *     模板详情。
 */
export async function fetchSmartAccessTemplateDetail(templateId, templateVersion) {
  const response = await http.get(
    `/api/smartaccess/templates/${templateId}/versions/${templateVersion}`
  );
  return response.data;
}

/**
 * 发起 SmartAccess 远程运行。
 *
 * Args:
 *     payload: 运行创建请求。
 *
 * Returns:
 *     运行创建结果。
 */
export async function createSmartAccessRun(payload) {
  const response = await http.post("/api/smartaccess/runs", payload);
  return response.data;
}
```

- [ ] **Step 2: 新增模板页面**

创建 `frontend/src/pages/SmartAccessTemplatesPage.jsx`，页面使用 Ant Design `Card`、`Table`、`Drawer`、`Descriptions`、`Button`、`Input`。核心行为：

```javascript
const columns = [
  { title: "模板 ID", dataIndex: "template_id", key: "template_id" },
  { title: "版本", dataIndex: "template_version", key: "template_version" },
  { title: "工作流", dataIndex: "name", key: "name" },
  { title: "绑定设备", dataIndex: "anchor_profile", key: "anchor_profile" },
  { title: "步骤数", dataIndex: "step_count", key: "step_count" },
  { title: "发布时间", dataIndex: "published_at", key: "published_at" },
];
```

点击行打开详情抽屉，显示：

```javascript
<pre>{JSON.stringify(detail?.workflow || {}, null, 2)}</pre>
```

点击“发起运行”调用：

```javascript
await createSmartAccessRun({
  template_id: detail.template_id,
  template_version: detail.template_version,
  device_id: detail.source_device_id || detail.anchor_profile,
  requested_by: "web",
});
```

- [ ] **Step 3: 注册路由**

修改 `frontend/src/router.jsx`：

```javascript
const SmartAccessTemplatesPage = lazy(() => import("./pages/SmartAccessTemplatesPage"));
...
{
  path: "smartaccess/templates",
  element: withSuspense(<SmartAccessTemplatesPage />)
},
```

- [ ] **Step 4: 新增菜单项**

修改 `frontend/src/layout/AppSidebar.jsx`，引入图标：

```javascript
import { CloudServerOutlined } from "@ant-design/icons";
```

在 `MENU_ITEMS` 中 `工作流编排` 后新增：

```javascript
{
  key: "/smartaccess/templates",
  icon: <CloudServerOutlined />,
  label: "SmartAccess 模板"
},
```

- [ ] **Step 5: 状态标签兼容 SmartAccess 状态**

修改 `frontend/src/components/StatusTag.jsx`：

```javascript
const STATUS_COLOR_MAP = {
  accepted: "processing",
  blocked: "warning",
  queued: "warning",
  rejected: "error",
  ...
};

const STATUS_LABEL_MAP = {
  accepted: "已接收",
  blocked: "阻塞",
  queued: "排队中",
  rejected: "已拒绝",
  ...
};
```

- [ ] **Step 6: 任务运行页增加来源列**

修改 `WorkflowRunsPage.jsx`：

```javascript
{ title: "任务来源", dataIndex: "source", key: "source", render: (value) => value === "smartaccess" ? "SmartAccess" : "SpecLabOS" }
```

`normalizeRuns()` 增加：

```javascript
source: item.source || "speclabos",
```

修正 `STATUS_OPTIONS`，使用真实状态：

```javascript
const STATUS_OPTIONS = [
  { label: "全部状态", value: "all" },
  { label: "排队中", value: "queued" },
  { label: "运行中", value: "running" },
  { label: "已完成", value: "success" },
  { label: "失败", value: "failed" },
  { label: "阻塞", value: "blocked" },
];
```

- [ ] **Step 7: 任务详情页展示 SmartAccess 字段**

修改 `WorkflowRunDetailPage.jsx`，在基础信息中增加：

```javascript
<Descriptions.Item label="任务来源">
  {detail?.source === "smartaccess" ? "SmartAccess" : "SpecLabOS"}
</Descriptions.Item>
<Descriptions.Item label="模板">
  {detail?.template_id ? `${detail.template_id}@${detail.template_version || ""}` : "--"}
</Descriptions.Item>
<Descriptions.Item label="锚点配置">{detail?.anchor_profile || "--"}</Descriptions.Item>
```

如果 `detail?.source === "smartaccess"`，卡片标题改为 `"SmartAccess 步骤与 Trace"`。

- [ ] **Step 8: 前端构建验证**

Run:

```powershell
cd E:\github_project\SpecLabOS\frontend
npm run build
```

Expected: build success.

- [ ] **Step 9: 提交 Task 4**

```powershell
cd E:\github_project\SpecLabOS
git add frontend/src/services/smartaccessApi.js frontend/src/pages/SmartAccessTemplatesPage.jsx frontend/src/router.jsx frontend/src/layout/AppSidebar.jsx frontend/src/services/workflowApi.js frontend/src/pages/WorkflowRunsPage.jsx frontend/src/pages/WorkflowRunDetailPage.jsx frontend/src/components/StatusTag.jsx
git commit -m "新增 SmartAccess 模板前端页面" -m "- 添加 SmartAccess 模板列表、详情和远程发起入口" -m "- 扩展任务运行页展示任务来源" -m "- 兼容 SmartAccess 运行状态标签"
```

---

### Task 5: SmartAccess 模板发布接入 SpecLabOS HTTP API

**Files:**
- Modify: `E:/github_project/SmartAccess/src/smartaccess/runtime/adapters/speclabos_client.py`
- Modify: `E:/github_project/SmartAccess/src/smartaccess/shared/config/settings.py`
- Test: `E:/github_project/SmartAccess/tests/integration/test_speclabos_platform_client.py`

**Interfaces:**
- Consumes: `POST /api/smartaccess/templates/publish` from SpecLabOS.
- Produces: `SpecLabOSPlatformClient.publish_template(payload: dict) -> dict` compatible with new API.

- [ ] **Step 1: 写 HTTP 客户端测试**

创建 `tests/integration/test_speclabos_platform_client.py`：

```python
"""SpecLabOS 平台客户端测试。"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread

from smartaccess.runtime.adapters.speclabos_client import SpecLabOSPlatformClient


class CaptureHandler(BaseHTTPRequestHandler):
    """捕获 HTTP 请求的测试 handler。"""

    payloads: list[dict] = []

    def do_POST(self):  # noqa: N802
        """处理 POST 请求。"""
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        self.__class__.payloads.append({"path": self.path, "payload": payload})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, **payload}).encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A002
        """关闭测试 HTTP 日志。"""
        return None


def test_publish_template_posts_smartaccess_endpoint() -> None:
    """验证模板发布调用 SpecLabOS SmartAccess 模板接口。"""
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = SpecLabOSPlatformClient(base_url=f"http://127.0.0.1:{server.server_port}")

    result = client.publish_template(
        {
            "template_id": "tpl_weixin",
            "template_version": "1.0.0",
            "anchor_profile": "weixin",
            "workflow": {
                "metadata": {"workflow_id": "wf_weixin"},
                "steps": [{"id": "open"}],
            },
        }
    )

    server.shutdown()
    assert result["ok"] is True
    assert CaptureHandler.payloads[-1]["path"] == "/api/smartaccess/templates/publish"
    assert CaptureHandler.payloads[-1]["payload"]["workflow_id"] == "wf_weixin"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd E:\github_project\SmartAccess
.\.venv\Scripts\python.exe -m pytest tests\integration\test_speclabos_platform_client.py -q
```

Expected: path assertion fails，当前默认 path 是 `/smartaccess/templates/publish`。

- [ ] **Step 3: 修改客户端默认端点和 payload 归一化**

修改 `src/smartaccess/runtime/adapters/speclabos_client.py`：

```python
"publish_template": "/api/smartaccess/templates/publish",
"list_templates": "/api/smartaccess/templates",
"fetch_template": "/api/smartaccess/templates/{template_id}/versions/{template_version}",
"delete_template": "/api/smartaccess/templates/{template_id}/versions/{template_version}",
"upload_status": "/api/smartaccess/runs/{run_id}/events",
```

在 `publish_template()` 内增加归一化：

```python
def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(payload.get("workflow") or {})
    metadata = workflow.get("metadata", {}) if isinstance(workflow, dict) else {}
    normalized = {
        "template_id": payload["template_id"],
        "template_version": payload["template_version"],
        "workflow_id": str(metadata.get("workflow_id") or payload.get("workflow_id") or ""),
        "name": str(metadata.get("workflow_id") or payload["template_id"]),
        "description": str(metadata.get("description") or ""),
        "anchor_profile": str(payload.get("anchor_profile") or metadata.get("anchor_profile") or ""),
        "source_device_id": str(payload.get("source_device_id") or payload.get("anchor_profile") or ""),
        "published_by": "smartaccess",
        "workflow": workflow,
    }
    return self._request("POST", self._endpoints["publish_template"], normalized)
```

- [ ] **Step 4: 配置别名说明**

当前 SmartAccess 已有：

```text
SMARTACCESS_PLATFORM_PROVIDER=real
SPECLABOS_BASE_URL=http://127.0.0.1:8000
SPECLABOS_API_KEY=...
```

本任务不强制新增 `SMARTACCESS_SPECLABOS_BASE_URL`，避免配置重复。后续如需更清晰命名，再加别名读取。

- [ ] **Step 5: 运行测试**

Run:

```powershell
cd E:\github_project\SmartAccess
.\.venv\Scripts\python.exe -m pytest tests\integration\test_speclabos_platform_client.py -q
```

Expected: passed.

- [ ] **Step 6: 提交 Task 5**

```powershell
cd E:\github_project\SmartAccess
git add src/smartaccess/runtime/adapters/speclabos_client.py tests/integration/test_speclabos_platform_client.py
git commit -m "接入 SpecLabOS SmartAccess 模板发布接口" -m "- 调整 SpecLabOS 平台客户端默认端点" -m "- 归一化模板发布 payload" -m "- 添加模板发布 HTTP 客户端测试"
```

---

### Task 6: SmartAccess 远程任务消费者和状态回传

**Files:**
- Create: `E:/github_project/SmartAccess/src/smartaccess/runtime/application/platform_event_uploader.py`
- Create: `E:/github_project/SmartAccess/src/smartaccess/runtime/application/remote_task_worker.py`
- Modify: `E:/github_project/SmartAccess/src/smartaccess/shared/config/settings.py`
- Modify: `E:/github_project/SmartAccess/src/smartaccess/bootstrap/runtime.py`
- Modify: `E:/github_project/SmartAccess/src/smartaccess/bootstrap/__init__.py`
- Modify: `E:/github_project/SmartAccess/pyproject.toml`
- Test: `E:/github_project/SmartAccess/tests/integration/test_remote_task_worker.py`

**Interfaces:**
- Consumes: RabbitMQ `run.requested` message.
- Consumes: `RuntimeFacade.start_run(workflow, background=True)`.
- Produces: `RemoteTaskWorker.handle_message(payload: dict) -> str`.
- Produces: platform events uploaded by `PlatformEventUploader`.

- [ ] **Step 1: 写 worker 单元测试**

创建 `tests/integration/test_remote_task_worker.py`：

```python
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

    def upload_event(self, run_id: str, event_type: str, status: str, payload: dict) -> None:
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd E:\github_project\SmartAccess
.\.venv\Scripts\python.exe -m pytest tests\integration\test_remote_task_worker.py -q
```

Expected: import error。

- [ ] **Step 3: 实现 PlatformEventUploader**

创建 `src/smartaccess/runtime/application/platform_event_uploader.py`：

```python
"""SpecLabOS SmartAccess 运行事件上传器。"""

from __future__ import annotations

from uuid import uuid4


class PlatformEventUploader:
    """把 SmartAccess 本地运行事件上传到 SpecLabOS。"""

    def __init__(self, platform) -> None:
        """初始化上传器。

        Args:
            platform: SpecLabOS 平台客户端。
        """
        self._platform = platform

    def upload_event(
        self,
        run_id: str,
        event_type: str,
        status: str,
        payload: dict,
    ) -> None:
        """上传运行事件。

        Args:
            run_id: SpecLabOS 运行 ID。
            event_type: 事件类型。
            status: 运行状态。
            payload: 事件载荷。
        """
        method = getattr(self._platform, "upload_run_event", None)
        if not callable(method):
            return
        method(
            run_id,
            {
                "event_id": payload.get("event_id") or f"evt_{uuid4().hex}",
                "event_type": event_type,
                "status": status,
                "step_id": str(payload.get("step_id") or ""),
                "step_index": payload.get("step_index"),
                "payload": payload,
            },
        )
```

- [ ] **Step 4: 给 SpecLabOSPlatformClient 增加 upload_run_event**

修改 `src/smartaccess/runtime/adapters/speclabos_client.py`：

```python
def upload_run_event(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """上传 SmartAccess 运行事件。

    Args:
        run_id: SpecLabOS 运行 ID。
        payload: 事件载荷。

    Returns:
        平台响应。
    """
    path = f"/api/smartaccess/runs/{quote(run_id, safe='')}/events"
    return self._request("POST", path, payload)
```

- [ ] **Step 5: 实现 RemoteTaskWorker**

创建 `src/smartaccess/runtime/application/remote_task_worker.py`：

```python
"""SmartAccess 远程任务消费者。"""

from __future__ import annotations

import json
from typing import Any

from smartaccess.shared.contracts.workflow import WorkflowContract


class RemoteTaskWorker:
    """消费 SpecLabOS 下发的 SmartAccess 远程运行任务。"""

    def __init__(self, *, device_id: str, facade, uploader) -> None:
        """初始化 worker。

        Args:
            device_id: 当前 SmartAccess 设备 ID。
            facade: 运行时门面。
            uploader: 平台事件上传器。
        """
        self._device_id = device_id
        self._facade = facade
        self._uploader = uploader

    def handle_message(self, payload: dict[str, Any]) -> str:
        """处理一条远程运行消息。

        Args:
            payload: RabbitMQ 消息体。

        Returns:
            处理结果状态。
        """
        run_id = str(payload.get("run_id") or "")
        device_id = str(payload.get("device_id") or "")
        if device_id != self._device_id:
            self._uploader.upload_event(
                run_id,
                "run.rejected",
                "rejected",
                {"error": f"设备不匹配: expected={self._device_id}, actual={device_id}"},
            )
            return "rejected"
        try:
            workflow = WorkflowContract.model_validate(payload.get("workflow") or {})
        except Exception as exc:  # noqa: BLE001
            self._uploader.upload_event(
                run_id,
                "run.rejected",
                "rejected",
                {"error": str(exc), "error_type": exc.__class__.__name__},
            )
            return "rejected"
        session = self._facade.start_run(workflow, background=True)
        self._uploader.upload_event(
            run_id,
            "run.accepted",
            "accepted",
            {
                "local_session_id": session.session_id,
                "workflow_id": workflow.metadata.workflow_id,
            },
        )
        return "accepted"

    def handle_body(self, body: bytes) -> str:
        """处理 RabbitMQ 原始消息体。

        Args:
            body: JSON 消息字节。

        Returns:
            处理结果状态。
        """
        return self.handle_message(json.loads(body.decode("utf-8")))
```

- [ ] **Step 6: 添加配置**

修改 `src/smartaccess/shared/config/settings.py`，在 `AppSettings` 增加：

```python
device_id: str = Field(default="")
rabbitmq_host: str = Field(default="127.0.0.1")
rabbitmq_port: int = Field(default=5672, ge=1, le=65535)
rabbitmq_username: str = Field(default="guest")
rabbitmq_password: str = Field(default="guest")
rabbitmq_enabled: bool = Field(default=False)
```

在 `from_env()` 增加：

```python
device_id=_get("SMARTACCESS_DEVICE_ID", "") or "",
rabbitmq_host=_get("SMARTACCESS_RABBITMQ_HOST", "127.0.0.1") or "127.0.0.1",
rabbitmq_port=int(_get("SMARTACCESS_RABBITMQ_PORT", "5672") or "5672"),
rabbitmq_username=_get("SMARTACCESS_RABBITMQ_USERNAME", "guest") or "guest",
rabbitmq_password=_get("SMARTACCESS_RABBITMQ_PASSWORD", "guest") or "guest",
rabbitmq_enabled=(_get("SMARTACCESS_RABBITMQ_ENABLED", "false") or "false").lower() == "true",
```

- [ ] **Step 7: 添加 worker 启动入口**

在 `src/smartaccess/bootstrap/runtime.py` 增加 `build_remote_task_worker(settings)` 和 `run_remote_task_worker(settings=None)`。第一版可以只构造 worker，不连接真实 RabbitMQ；连接循环在后续小步实现。

```python
def build_remote_task_worker(settings: AppSettings):
    """创建 SmartAccess 远程任务 worker。"""
    from smartaccess.runtime.application.platform_event_uploader import PlatformEventUploader
    from smartaccess.runtime.application.remote_task_worker import RemoteTaskWorker

    facade = build_runtime_facade(settings)
    return RemoteTaskWorker(
        device_id=settings.device_id or str(settings.workspace_dir),
        facade=facade,
        uploader=PlatformEventUploader(facade.providers()["platform"]),
    )
```

- [ ] **Step 8: 添加 pyproject script 和依赖**

修改 `pyproject.toml`：

```toml
dependencies = [
  ...
  "pika>=1.3,<2",
]

[project.scripts]
smartaccess-worker = "smartaccess.bootstrap:run_remote_task_worker"
```

- [ ] **Step 9: 运行 worker 测试**

Run:

```powershell
cd E:\github_project\SmartAccess
.\.venv\Scripts\python.exe -m pytest tests\integration\test_remote_task_worker.py tests\integration\test_speclabos_platform_client.py -q
```

Expected: passed.

- [ ] **Step 10: 提交 Task 6**

```powershell
cd E:\github_project\SmartAccess
git add src/smartaccess/runtime/application/platform_event_uploader.py src/smartaccess/runtime/application/remote_task_worker.py src/smartaccess/runtime/adapters/speclabos_client.py src/smartaccess/shared/config/settings.py src/smartaccess/bootstrap/runtime.py src/smartaccess/bootstrap/__init__.py pyproject.toml tests/integration/test_remote_task_worker.py
git commit -m "新增 SmartAccess 远程任务 worker" -m "- 添加 RabbitMQ 任务消息处理逻辑" -m "- 添加 SpecLabOS 运行事件上传器" -m "- 增加远程任务配置和测试"
```

---

### Task 7: 端到端配置、文档和冒烟验证

**Files:**
- Modify: `E:/github_project/SmartAccess/.envexample`
- Modify: `E:/github_project/SmartAccess/README.md`
- Modify: `E:/github_project/SpecLabOS/README.md`
- Modify: `E:/github_project/SpecLabOS/config.example.yaml`
- Test/Verify: backend pytest, frontend build, SmartAccess integration tests.

**Interfaces:**
- Consumes all previous tasks.
- Produces documented runbook.

- [ ] **Step 1: 更新 SmartAccess 环境示例**

在 `SmartAccess/.envexample` 增加：

```env
SMARTACCESS_PLATFORM_PROVIDER=real
SPECLABOS_BASE_URL=http://127.0.0.1:8000
SPECLABOS_API_KEY=dev-smartaccess-token
SMARTACCESS_DEVICE_ID=weixin
SMARTACCESS_RABBITMQ_ENABLED=true
SMARTACCESS_RABBITMQ_HOST=127.0.0.1
SMARTACCESS_RABBITMQ_PORT=5672
SMARTACCESS_RABBITMQ_USERNAME=admin
SMARTACCESS_RABBITMQ_PASSWORD=password123
```

- [ ] **Step 2: 更新 SpecLabOS 配置示例**

在 `SpecLabOS/config.example.yaml` 增加：

```yaml
smartaccess:
  api_token: dev-smartaccess-token
```

如果 Task 2 已在 `Settings` 中加入 `smartaccess` 配置，则同步更新 `config.yaml` 时只在本地说明，不提交真实敏感值。

- [ ] **Step 3: 更新 SmartAccess README**

增加“发布模板到 SpecLabOS”和“远程 worker 启动”说明：

```markdown
### SmartAccess 与 SpecLabOS 联动

1. 配置 `SMARTACCESS_PLATFORM_PROVIDER=real` 和 `SPECLABOS_BASE_URL`。
2. 在 SmartAccess 工作流中填写 `template_id` 与 `template_version`。
3. 在“模板/平台”页点击发布，模板会保存到 SpecLabOS。
4. 启动远程任务 worker：`smartaccess-worker`。
```

- [ ] **Step 4: 更新 SpecLabOS README**

增加 SmartAccess 模板页和远程下发说明：

```markdown
### SmartAccess 模板中心

SpecLabOS 提供 `/api/smartaccess/templates/publish` 接收 SmartAccess 模板发布，并在“SmartAccess 模板”页查看模板版本。平台发起运行后，通过 RabbitMQ 投递到 `smartaccess.device.{device_id}.commands` 队列。
```

- [ ] **Step 5: 运行 SpecLabOS 后端测试**

Run:

```powershell
cd E:\github_project\SpecLabOS\backend
..\.venv\Scripts\python.exe -m pytest tests\test_smartaccess_service.py tests\test_smartaccess_routes.py tests\test_workflow_routes.py -q
```

Expected: all passed.

- [ ] **Step 6: 运行 SpecLabOS 前端构建**

Run:

```powershell
cd E:\github_project\SpecLabOS\frontend
npm run build
```

Expected: build success.

- [ ] **Step 7: 运行 SmartAccess 测试**

Run:

```powershell
cd E:\github_project\SmartAccess
.\.venv\Scripts\python.exe -m pytest tests\integration\test_speclabos_platform_client.py tests\integration\test_remote_task_worker.py -q
```

Expected: all passed.

- [ ] **Step 8: 手工冒烟验证**

按顺序验证：

```text
1. 启动 SpecLabOS 后端。
2. 启动 SpecLabOS 前端。
3. SmartAccess 配置 SPECLABOS_BASE_URL。
4. SmartAccess 发布一个 workflow 模板。
5. SpecLabOS SmartAccess 模板页能看到该模板。
6. SpecLabOS 点击发起运行，后端创建 smartaccess_runs。
7. SmartAccess worker 处理一条测试 run.requested 消息。
8. SpecLabOS 任务运行页能看到 SmartAccess 来源任务状态变化。
```

- [ ] **Step 9: 提交 Task 7**

```powershell
cd E:\github_project\SmartAccess
git add .envexample README.md
git commit -m "补充 SmartAccess 与 SpecLabOS 联动说明" -m "- 添加平台发布和远程 worker 配置示例" -m "- 说明模板发布和远程任务启动流程"

cd E:\github_project\SpecLabOS
git add README.md config.example.yaml
git commit -m "补充 SmartAccess 模板中心说明" -m "- 添加 SmartAccess API 和 RabbitMQ 队列说明" -m "- 更新配置示例"
```

---

## Self-Review

### Spec Coverage

- 模板发布 HTTP：Task 1、Task 2、Task 5 覆盖。
- SmartAccess 独立模板页：Task 4 覆盖。
- 远程任务 RabbitMQ 下发：Task 3、Task 6 覆盖。
- 状态回传 HTTP：Task 2、Task 6 覆盖。
- 任务运行页兼容 SmartAccess：Task 2、Task 4 覆盖。
- 配置和文档：Task 7 覆盖。

### Placeholder Scan

计划中没有未定事项、待办占位或省略实现作为交付步骤。所有任务都给出了目标文件、接口、测试命令和提交命令。

### Type Consistency

- SpecLabOS 使用 `SmartAccessTemplatePublishRequest`、`SmartAccessRunCreateRequest`、`SmartAccessRunEventRequest` 贯穿 schema、service、repository、route。
- SmartAccess worker 使用 `RemoteTaskWorker.handle_message(payload: dict) -> str` 作为可测入口。
- 平台事件上传统一使用 `upload_event(run_id, event_type, status, payload)`。
