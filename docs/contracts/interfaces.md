# SmartAccess 关键契约与样例

## 1. 目的

本文统一定义 SmartAccess 运行时最重要的五类契约，并补充设备侧 FastAPI MVP 基线接口。它们不是最终代码实现，而是后续桌面端、AI 组件、平台适配和评测体系共享的结构基线。

## 2. 契约列表

| 契约 | 作用 | 生产者 | 消费者 | 样例 |
| --- | --- | --- | --- | --- |
| `workflow.yaml` | 定义实验工作流与模板身份 | AI workflow 设计器、人工编辑器 | orchestrator、executor | [workflow.yaml](examples/workflow.yaml) |
| `instrument_profile.yaml` | 定义仪器画像和界面锚点 | 校准会话、接入工程师 | orchestrator、executor、observer | [instrument_profile.yaml](examples/instrument_profile.yaml) |
| `platform_adapter.yaml` | 定义平台接口、模板同步接口和字段映射 | 平台适配配置器 | orchestrator、platform client | [platform_adapter.yaml](examples/platform_adapter.yaml) |
| `run_trace.jsonl` | 定义运行轨迹日志 | executor、observer、recovery | 审计、监控、补传任务 | [run_trace.jsonl](examples/run_trace.jsonl) |
| `eval_case.yaml` | 定义回归评测场景 | QA/自动化工程师 | eval harness | [eval_case.yaml](examples/eval_case.yaml) |

## 3. `workflow.yaml`

### 3.1 用途

描述一次实验任务如何被拆解为可执行步骤，并声明模板身份、前置条件、ROI 绑定、输出项和重试策略。

### 3.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `metadata.workflow_id` | 工作流实例或草稿标识 |
| `metadata.template_id` | 稳定模板标识，用于发布、回拉和审计 |
| `metadata.template_version` | 模板版本标识，用于 SpecLabOS 模板中心和任务下发 |
| `metadata.author` | 工作流作者或发布来源 |
| `metadata.instrument_profile` | 适用仪器画像 |
| `metadata.experiment_type` | 目标实验类型 |
| `metadata.lifecycle_state` | 当前模板生命周期状态，如 `Draft`、`Standardized`、`Published` |
| `preconditions` | 执行前必须满足的条件 |
| `roi_bindings` | 步骤依赖的视觉区域与读数绑定 |
| `steps` | 具体执行步骤序列 |
| `outputs` | 期望输出的数据、文件、状态 |
| `retry_policy` | 全局或步骤级重试规则 |

### 3.3 责任边界

- workflow 负责描述意图、模板身份和顺序，不负责保存真实截图内容。
- orchestrator 负责解释 workflow，并在执行前确认其来源于本地草稿还是平台回拉模板。
- `template_id` 与 `template_version` 是发布态模板的稳定语义，不能用运行时 `request_id` 替代。

## 4. `instrument_profile.yaml`

### 4.1 用途

描述某一类仪器上位机的窗口签名、锚点、动作能力和安全限制。

### 4.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `device_id` | 仪器画像唯一标识 |
| `supported_os` | 支持的操作系统 |
| `window_signature` | 识别窗口所需的标题、尺寸、控件线索 |
| `anchors` | 按钮、输入框、读数区等界面锚点 |
| `actions` | 允许使用的动作集合 |
| `safety_limits` | 禁止或限制的参数范围与动作条件 |

### 4.3 责任边界

- instrument profile 不保存一次性运行结果。
- observer 和 executor 共享它，但不得绕过安全限制。

## 5. `platform_adapter.yaml`

### 5.1 用途

定义 SmartAccess 与 SpecLabOS 的接口地址、认证方式、任务/模板/状态映射和重试策略。

### 5.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `base_url` | 平台 API 基地址 |
| `auth` | 认证模式和密钥引用方式 |
| `endpoint_map.health` | 设备侧健康检查接口 |
| `endpoint_map.fetch_task` | 平台任务拉取接口 |
| `endpoint_map.fetch_template` | 平台模板拉取接口 |
| `endpoint_map.publish_template` | 标准模板发布到 SpecLabOS 的接口 |
| `endpoint_map.upload_status` | 运行状态上传接口 |
| `endpoint_map.upload_logs` | 运行日志上传接口 |
| `endpoint_map.upload_results` | 运行结果上传接口 |
| `field_map` | 本地字段到平台字段的映射 |
| `retry_policy` | 接口失败后的重试和补传规则 |

### 5.3 责任边界

- 该文件定义接口契约，不直接保存访问令牌明文。
- 真正的密钥管理应由安全配置层接管。
- `fetch_task` 负责返回任务上下文和模板引用，`fetch_template` 负责根据模板 ID 与版本返回模板内容，二者职责必须分离。

## 6. 设备侧 FastAPI MVP 基线接口

### 6.1 目标

为 SmartAccess 在设备侧暴露统一的实验触发、执行和状态查询能力，接口形态参考 `docs/refer/fastapi_service.py`。

### 6.2 端点定义

| 端点 | 方法 | 作用 |
| --- | --- | --- |
| `/health` | `GET` | 服务健康检查与联通性确认 |
| `/api/v1/experiment/trigger` | `POST` | 提交 `experiment_plan`，生成本地执行指令，返回 `request_id` |
| `/api/v1/experiment/execute` | `POST` | 基于最近一次成功生成的流程发起执行 |
| `/api/v1/experiment/status` | `GET` | 查询当前执行状态、当前命令、最近触发时间和最新请求标识 |

### 6.3 调用顺序

1. 运维或平台侧先调用 `/health` 确认服务可用。
2. 平台或本地用户调用 `/api/v1/experiment/trigger` 生成本地执行指令。
3. 只有在 `trigger` 成功完成后，才允许调用 `/api/v1/experiment/execute`。
4. 执行启动后，通过 `/api/v1/experiment/status` 轮询当前执行进展。

### 6.4 失败语义

- 当上一轮生成仍在执行中时，`trigger` 应拒绝并返回冲突语义。
- 当未成功触发或指令生成失败时，`execute` 应拒绝执行。
- `status` 是只读轮询接口，不承担暂停、恢复、终止等控制能力。
- 下游 UDP/执行器失败、模板解析失败和状态查询失败，应作为不同异常类型记录到运行轨迹和平台日志。

## 7. `run_trace.jsonl`

### 7.1 用途

定义一次运行过程中按时间顺序记录的动作、观察和结果事件。

### 7.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 事件时间 |
| `session_id` | 会话唯一标识 |
| `step_id` | 工作流步骤标识 |
| `observation` | 截图、OCR、状态判断等观察结果 |
| `action` | 本次动作或恢复动作 |
| `result` | 执行结果与状态 |
| `artifacts` | 截图、日志、结果文件等产物引用 |

### 7.3 责任边界

- 采用 JSONL 方便流式写入和补传。
- 运行轨迹是审计主线，不等于平台展示模型。
- 与模板相关的事件应能够标识 `template_id`、`template_version` 和来源。

## 8. `eval_case.yaml`

### 8.1 用途

定义回归评测中的单个场景，包括输入、预期事件和通过标准。

### 8.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `scenario` | 场景标识与目标 |
| `inputs` | 所需工作流、仪器画像、截图或模拟数据 |
| `expected_events` | 期望发生的动作、观察或回传 |
| `pass_criteria` | 通过条件 |
| `fixtures` | 附件、模拟服务或基线截图 |

### 8.3 责任边界

- eval case 只定义场景和标准，不直接承载实现代码。
- eval harness 负责读取它并执行评测。
- 平台同步类评测应同时覆盖模板同步与状态回传，而不只覆盖结果上传。

## 9. 建议实现原则

- 字段命名以稳定、可扩展和可读为优先。
- 任何新增字段都应补充文档和样例。
- 真实代码实现前，应先更新本目录中的契约说明。
- 模板中心语义优先于临时运行态语义，避免把执行态字段反向滥用为模板标识。
