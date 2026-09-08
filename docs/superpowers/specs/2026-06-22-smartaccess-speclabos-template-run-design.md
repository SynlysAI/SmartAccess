# SmartAccess 与 SpecLabOS 模板发布和远程任务联动设计

## 背景

SmartAccess 当前已经具备本地工作流设计、模板发布入口、本地执行和运行 trace 记录能力，但模板发布默认只落到本地 `workspace/templates`，平台侧使用的是内存 stub。SpecLabOS 当前已有 FastAPI、MongoDB、React 前端、工作流编排和任务运行页，但现有工作流模型面向 SpecLabOS 内置设备动作，和 SmartAccess 的 `workflow.yaml` 契约不是同一类执行模型。

本设计目标是在不破坏 SpecLabOS 现有工作流编排功能的前提下，新增 SmartAccess 模板中心和远程任务下发闭环。

## 目标

1. SmartAccess 可以把已经创建好的工作流模板发布到 SpecLabOS。
2. SpecLabOS 可以远程查看 SmartAccess 模板、版本、步骤和原始 workflow 快照。
3. SpecLabOS 可以针对指定 SmartAccess 设备发起工作流运行。
4. SmartAccess 设备端可以消费分配给自己的任务，执行本地 workflow。
5. SmartAccess 可以把运行状态、步骤事件和 trace 摘要回传给 SpecLabOS。
6. SpecLabOS 的任务运行页可以查看 SmartAccess 任务状态和详情。

## 非目标

1. 不把 SmartAccess workflow 强行塞进现有 SpecLabOS 工作流编排页。
2. 不让 SmartAccess 直接写 MongoDB 作为长期主路径。
3. 第一版不上传截图二进制文件，只保存 SmartAccess 本地截图路径和 trace 摘要。
4. 第一版不做复杂模板审批、权限细分、模板市场和版本回滚治理。

## 总体架构

采用 **HTTP 管理接口 + RabbitMQ 任务下发 + MongoDB 状态持久化** 的混合模式。

```text
SmartAccess 发布模板
  -> POST /api/smartaccess/templates/publish
  -> SpecLabOS 后端校验并写入 MongoDB

SpecLabOS 前端查看模板
  -> GET /api/smartaccess/templates
  -> SpecLabOS 后端读取 MongoDB

SpecLabOS 前端发起远程运行
  -> POST /api/smartaccess/runs
  -> SpecLabOS 后端创建 smartaccess_runs
  -> SpecLabOS 后端发送 RabbitMQ 任务到指定设备队列

SmartAccess 设备端
  -> 消费自己的 RabbitMQ 队列
  -> 使用消息中的 workflow 快照启动本地执行
  -> POST /api/smartaccess/runs/{run_id}/events 回传状态和步骤事件

SpecLabOS 任务运行页
  -> 读取普通 workflow_runs 和 smartaccess_runs
  -> 统一展示任务来源、状态和详情
```

## 设计取舍

### 模板发布使用 HTTP

模板发布是同步管理操作，用户点击发布后需要立即知道成功或失败。使用 HTTP 可以让 SpecLabOS 后端统一负责 workflow 校验、版本冲突、发布来源、审计字段和 MongoDB schema。

### 远程任务下发使用 RabbitMQ

远程执行是异步任务，设备可能离线或正在运行。RabbitMQ 更适合把任务投递到指定设备队列，SmartAccess 不需要暴露本机 HTTP 服务，SpecLabOS 也不需要知道设备电脑的 IP。

### 状态回传第一版使用 HTTP

状态回传先使用 HTTP，原因是实现和排障更直接。SmartAccess 端已经有本地运行事件和 trace，第一版可以把这些事件异步投递到 SpecLabOS HTTP API。后续如果事件量大或需要更强削峰能力，再把回传通道替换成 RabbitMQ 事件流。

### 不直接写 MongoDB

SmartAccess 直接写 MongoDB 虽然实现最快，但会让 SmartAccess 持有平台数据库账号和集合结构，导致权限边界、schema 演进、校验和审计规则分散。长期设计中，SpecLabOS 后端应该是平台数据唯一写入口。

## SpecLabOS 后端设计

### 新增模块

```text
backend/app/api/routes/smartaccess.py
backend/app/schemas/smartaccess.py
backend/app/repositories/smartaccess_repository.py
backend/app/services/smartaccess_service.py
backend/app/services/smartaccess_mq.py
```

### MongoDB 集合

#### `smartaccess_templates`

保存 SmartAccess 发布的模板版本快照。

核心字段：

```json
{
  "template_id": "tpl_weixin_login",
  "template_version": "1.0.0",
  "workflow_id": "weixin_test",
  "name": "微信登录流程",
  "description": "",
  "anchor_profile": "weixin",
  "source_device_id": "weixin",
  "source": "smartaccess",
  "status": "published",
  "step_count": 5,
  "workflow": {},
  "published_by": "smartaccess",
  "published_at": "2026-06-22T10:00:00Z",
  "updated_at": "2026-06-22T10:00:00Z"
}
```

唯一键：

```text
template_id + template_version
```

#### `smartaccess_runs`

保存平台发起的 SmartAccess 远程运行记录。

核心字段：

```json
{
  "run_id": "sa_run_20260622_001",
  "template_id": "tpl_weixin_login",
  "template_version": "1.0.0",
  "workflow_id": "weixin_test",
  "workflow_name": "微信登录流程",
  "device_id": "weixin",
  "anchor_profile": "weixin",
  "status": "queued",
  "current_step_index": 0,
  "total_steps": 5,
  "requested_by": "admin",
  "requested_at": "2026-06-22T10:10:00Z",
  "started_at": null,
  "finished_at": null,
  "workflow_snapshot": {},
  "summary": {},
  "last_error": ""
}
```

状态枚举：

```text
queued
accepted
running
blocked
success
failed
cancelled
rejected
```

#### `smartaccess_run_events`

保存 SmartAccess 回传的运行事件和步骤 trace 摘要。

核心字段：

```json
{
  "event_id": "evt_001",
  "run_id": "sa_run_20260622_001",
  "event_type": "step.updated",
  "step_id": "open_window",
  "step_index": 1,
  "status": "success",
  "payload": {},
  "created_at": "2026-06-22T10:11:00Z"
}
```

### HTTP API

#### 发布模板

```text
POST /api/smartaccess/templates/publish
```

请求体：

```json
{
  "template_id": "tpl_weixin_login",
  "template_version": "1.0.0",
  "workflow_id": "weixin_test",
  "name": "微信登录流程",
  "description": "",
  "anchor_profile": "weixin",
  "source_device_id": "weixin",
  "published_by": "smartaccess",
  "workflow": {}
}
```

行为：

1. 校验 `template_id`、`template_version`、`workflow` 必填。
2. 从 `workflow` 中提取步骤数量、绑定锚点配置和 workflow 标识。
3. 使用 `template_id + template_version` upsert 模板快照。
4. 返回发布后的模板摘要。

#### 模板列表

```text
GET /api/smartaccess/templates?keyword=&device_id=&status=
```

返回模板版本列表，用于 SmartAccess 模板页。

#### 模板详情

```text
GET /api/smartaccess/templates/{template_id}/versions/{template_version}
```

返回模板元数据和完整 workflow 快照。

#### 发起运行

```text
POST /api/smartaccess/runs
```

请求体：

```json
{
  "template_id": "tpl_weixin_login",
  "template_version": "1.0.0",
  "device_id": "weixin",
  "requested_by": "admin"
}
```

行为：

1. 读取对应模板版本。
2. 创建 `smartaccess_runs` 记录，状态为 `queued`。
3. 发送 RabbitMQ 任务消息到指定设备队列。
4. 返回 `run_id`。

#### SmartAccess 运行列表

```text
GET /api/smartaccess/runs?keyword=&status=&device_id=
```

返回 SmartAccess 远程运行记录。

#### SmartAccess 运行详情

```text
GET /api/smartaccess/runs/{run_id}
```

返回运行基础信息、步骤列表、事件摘要和 trace 摘要。

#### 状态事件回传

```text
POST /api/smartaccess/runs/{run_id}/events
```

请求体：

```json
{
  "event_id": "evt_001",
  "event_type": "step.updated",
  "status": "success",
  "step_id": "open_window",
  "step_index": 1,
  "payload": {
    "actual_text": "登录成功",
    "expected_text": "登录成功",
    "matched": true,
    "screenshot_path": "runs/run_x/screenshots/open_window.png"
  }
}
```

行为：

1. 使用 `event_id` 做幂等去重。
2. 写入 `smartaccess_run_events`。
3. 根据事件类型更新 `smartaccess_runs` 的状态、进度、错误和摘要。

### RabbitMQ 任务消息

#### Exchange

```text
smartaccess.commands
```

#### Routing Key

```text
device.{device_id}.run.requested
```

#### Queue

```text
smartaccess.device.{device_id}.commands
```

#### 消息体

```json
{
  "message_id": "msg_001",
  "type": "run.requested",
  "run_id": "sa_run_20260622_001",
  "template_id": "tpl_weixin_login",
  "template_version": "1.0.0",
  "device_id": "weixin",
  "workflow": {},
  "requested_by": "admin",
  "requested_at": "2026-06-22T10:10:00Z"
}
```

SmartAccess 消费成功后 ack；如果本地校验失败，回传 `rejected` 事件并 ack，避免同一坏任务无限重试。

## SpecLabOS 前端设计

### 新增侧边栏入口

新增一级菜单：

```text
SmartAccess 模板
```

建议位置：

```text
设备监控
工作流编排
SmartAccess 模板
任务运行
设备日志
工具服务
```

### 新增页面

```text
frontend/src/pages/SmartAccessTemplatesPage.jsx
frontend/src/services/smartaccessApi.js
```

页面功能：

1. 模板列表：模板 ID、版本、绑定设备、步骤数、状态、发布时间。
2. 模板详情抽屉或详情区域：基础信息、workflow JSON/YAML 预览。
3. 发起运行按钮：选择目标设备后调用 `POST /api/smartaccess/runs`。
4. 最近运行：展示该模板最近 SmartAccess 运行记录。

### 改造任务运行页

现有 `WorkflowRunsPage.jsx` 保留，但列表数据源扩展为统一运行记录。

新增列：

```text
任务来源: SpecLabOS / SmartAccess
```

普通运行仍读取现有 `workflow_runs`，SmartAccess 运行读取 `smartaccess_runs`。后端可以提供统一接口，也可以前端分别请求后合并。第一版推荐后端提供统一接口，减少前端合并逻辑。

详情页 `WorkflowRunDetailPage.jsx` 根据 `source` 展示：

1. `source = speclabos`：沿用现有步骤时间线。
2. `source = smartaccess`：展示 SmartAccess 步骤状态、OCR 结果、trace 摘要和错误详情。

## SmartAccess 设计

### 配置

新增配置项：

```text
SMARTACCESS_SPECLABOS_BASE_URL
SMARTACCESS_SPECLABOS_API_KEY
SMARTACCESS_DEVICE_ID
SMARTACCESS_RABBITMQ_HOST
SMARTACCESS_RABBITMQ_PORT
SMARTACCESS_RABBITMQ_USERNAME
SMARTACCESS_RABBITMQ_PASSWORD
SMARTACCESS_RABBITMQ_ENABLED
```

`SMARTACCESS_DEVICE_ID` 用于决定当前 SmartAccess 消费哪个设备队列。

### HTTP 客户端

新增 SpecLabOS 客户端，负责：

1. 发布模板。
2. 上传运行事件。
3. 上传运行完成或失败摘要。

发布时复用当前 `TemplateService.publish()` 的本地保存逻辑，但平台发布目标改为 SpecLabOS HTTP API。

### MQ 消费者

新增 SmartAccess RabbitMQ 任务消费者：

1. 启动后绑定 `smartaccess.device.{device_id}.commands` 队列。
2. 收到 `run.requested` 后校验 `device_id` 和 workflow。
3. 把消息中的 workflow 快照转换为 `WorkflowContract`。
4. 调用现有 `RuntimeFacade.start_run(workflow, background=True)`。
5. 建立平台 `run_id` 和本地 `session_id` 的映射。
6. 订阅运行事件，按映射上传状态事件到 SpecLabOS。

第一版消费者可以作为独立命令启动，避免影响桌面主线程：

```text
smartaccess-worker
```

后续可以在桌面端增加开关，在 UI 内启动或停止消费者。

### 运行事件映射

SmartAccess 本地事件映射为平台事件：

```text
RUN_CREATED -> accepted
RUN_STARTED -> running
RUN_STEP_STARTED -> step.updated/running
RUN_STEP_OBSERVED -> step.updated/running + OCR 摘要
RUN_STEP_COMPLETED -> step.updated/success
RUN_BLOCKED -> blocked
RUN_COMPLETED -> success
RUN_FAILED -> failed
RUN_CANCELLED -> cancelled
```

## 错误处理

### 模板发布失败

如果 SpecLabOS HTTP API 不可用，SmartAccess 保留本地模板副本，并在模板页展示错误。第一版不要求自动补发模板；后续可复用本地 outbox 做补发。

### 任务下发失败

SpecLabOS 创建 run 后发送 MQ 失败时：

1. `smartaccess_runs.status = failed`
2. `last_error` 记录 MQ 错误
3. API 返回失败，前端提示用户重试

### SmartAccess 消费任务失败

如果 workflow 校验失败或设备不匹配：

1. SmartAccess 回传 `rejected` 事件。
2. SmartAccess ack 消息，避免坏任务重复执行。
3. SpecLabOS 标记 run 为 `rejected`。

### 状态回传失败

第一版 SmartAccess 使用本地 outbox 记录未上传事件，后台重试。事件包含 `event_id`，SpecLabOS 按 `event_id` 幂等写入。

## 鉴权

第一版使用 Bearer Token：

```text
Authorization: Bearer <SMARTACCESS_SPECLABOS_API_KEY>
```

SpecLabOS 后端新增 SmartAccess API Token 校验。Token 可以先复用配置文件中的固定值，后续再纳入用户和设备权限体系。

RabbitMQ 使用配置中的用户名密码。每台设备队列的权限隔离可以后续在 RabbitMQ 用户或 vhost 层实现。

## 测试策略

### SpecLabOS 后端

1. 模板发布 API：新增模板、覆盖同版本、列表查询、详情查询。
2. 发起运行 API：模板存在时创建 run 并调用 MQ publisher。
3. 状态事件 API：事件幂等、状态推进、步骤结果写入。
4. 统一任务运行接口：同时返回普通工作流和 SmartAccess 运行。

### SpecLabOS 前端

1. SmartAccess 模板页渲染空列表、正常列表、详情预览。
2. 发起运行成功和失败提示。
3. 任务运行页展示 SmartAccess 来源和详情。

### SmartAccess

1. 模板发布调用 SpecLabOS API，并保留本地副本。
2. MQ 消费者只消费匹配 `device_id` 的任务。
3. 收到任务后能启动本地 workflow。
4. 本地运行事件能转换并上传为 SpecLabOS 运行事件。

## 分阶段实施

### 阶段一：平台数据和 HTTP 闭环

1. SpecLabOS 新增 SmartAccess schema、repository、service 和 API。
2. SpecLabOS 新增模板页。
3. SmartAccess 发布按钮改为调用 SpecLabOS 模板发布 API。
4. 状态回传 API 和基础事件落库。

### 阶段二：RabbitMQ 远程下发

1. SpecLabOS 增加 RabbitMQ publisher。
2. SmartAccess 增加 RabbitMQ consumer。
3. 平台模板页支持发起运行。
4. SmartAccess 消费任务并启动本地执行。

### 阶段三：统一任务运行页

1. SpecLabOS 后端统一普通运行和 SmartAccess 运行列表。
2. 前端任务运行页增加来源列。
3. 详情页适配 SmartAccess trace 摘要。

## 验收标准

1. 在 SmartAccess 工作流页创建并保存 workflow 后，可在模板/平台页发布到 SpecLabOS。
2. SpecLabOS 的 SmartAccess 模板页能看到该模板版本和 workflow 内容。
3. 在 SpecLabOS 点击发起运行后，指定设备 SmartAccess 能消费任务。
4. SmartAccess 执行任务后，SpecLabOS 能看到运行状态从 `queued` 推进到 `running` 和最终状态。
5. SpecLabOS 任务运行详情能看到 SmartAccess 步骤事件和 OCR 摘要。
6. SmartAccess 离线时，SpecLabOS 发起的任务不会要求平台直接访问设备电脑。
