# SmartAccess 关键契约与样例

## 1. 目的

本文统一定义 SmartAccess v2 运行时最重要的五类契约，并补充设备侧 FastAPI MVP 基线接口。v2 主模型收敛为“锚点 -> 工作流 -> 执行”：锚点是可操作区域，每个锚点最多绑定一个可选 OCR 观测区域；工作流只描述线性步骤；运行 trace 自动记录 OCR 事实和执行结果。

## 2. 计划评审结论

本次简化重构计划方向正确，建议按断代替换执行，而不是在 UI 上隐藏旧字段。需要落实的关键修正如下：

- 保留 `模板/平台` 为一级入口，它负责新简化 workflow 的发布、回拉和平台字段适配。
- 对外契约使用 `anchors.yaml` 作为锚点集配置。
- 工作流不再提供用户手工结果声明；平台需要结果时从 `run_trace.jsonl` 的步骤级 OCR 事实读取。
- 公开契约只保留锚点集、线性步骤、OCR 预期和 trace 事实四类概念。
- 运行器只保留动作执行后的 OCR 轮询或默认等待，视觉 provider 收敛为截图、裁剪、OCR 读取和文本匹配。
- UI 主导航改为四个一级页面：`锚点`、`工作流`、`模板/平台`、`执行`。

## 3. 契约列表

| 契约 | 作用 | 生产者 | 消费者 | 样例 |
| --- | --- | --- | --- | --- |
| `anchors.yaml` | 定义窗口签名、动作锚点和可选 OCR 观测区域 | 锚点页、接入工程师 | workflow service、orchestrator、executor、observer | [anchors.yaml](examples/anchors.yaml) |
| `workflow.yaml` | 定义线性执行步骤与模板身份 | AI workflow 设计器、人工编辑器、模板回拉 | workflow service、orchestrator、executor | [workflow.yaml](examples/workflow.yaml) |
| `platform_adapter.yaml` | 定义平台接口、模板同步接口和字段映射 | 平台适配配置器 | platform client、template service、sync service | [platform_adapter.yaml](examples/platform_adapter.yaml) |
| `run_trace.jsonl` | 定义步骤级事实运行轨迹 | run service、executor、observer | 执行页、审计、平台补传任务 | [run_trace.jsonl](examples/run_trace.jsonl) |
| `eval_case.yaml` | 定义回归评测场景 | QA/自动化工程师 | eval harness | [eval_case.yaml](examples/eval_case.yaml) |

能力示例补充：

- [serial_debug_assistant_udp](examples/serial_debug_assistant_udp/)：串口调试助手 UDP 服务打开、消息发送和日志 OCR。
- [windows_calculator](examples/windows_calculator/)：Windows 计算器 `12+34=46` 运算和结果 OCR。

## 4. `anchors.yaml`

### 4.1 用途

描述一个上位机窗口中的可执行锚点集合。锚点是动作入口，不是自由 ROI 库；每个锚点固定包含动作区域，可选包含一个动作后 OCR 观测区域。

### 4.2 顶层字段

| 字段 | 说明 |
| --- | --- |
| `profile_id` | 锚点集唯一标识，用于 workflow 的 `metadata.anchor_profile` 引用 |
| `window_signature` | 定位窗口所需的标题、进程、尺寸或截图基准信息 |
| `anchors` | 锚点数组，每个锚点可执行动作并可携带一个观测区域 |

### 4.3 Anchor 字段

| 字段 | 说明 |
| --- | --- |
| `id` | 锚点唯一标识 |
| `label` | 面向用户展示的名称 |
| `action_region` | 动作区域，必须同时保存 `pixel` 和 `normalized` 坐标 |
| `observe_region` | 可选 OCR 观测区域，同样保存 `pixel` 和 `normalized` 坐标 |
| `supported_actions` | 允许在该锚点执行的动作集合 |
| `default_wait_seconds` | 无 OCR 预期时的默认等待秒数 |
| `notes` | 可选说明，用于人工维护和交接 |

### 4.4 责任边界

- `anchors.yaml` 不保存运行结果、平台结果声明、视觉基准或识别阈值。
- `action_region` 用于点击和聚焦，`observe_region` 只用于动作后的 OCR 判断。
- 坐标必须同时保存像素坐标和归一化坐标；运行时优先按当前窗口尺寸用归一化坐标重映射。
- 一个锚点最多绑定一个观测区域，避免重新引入额外区域映射层。

## 5. `workflow.yaml`

### 5.1 用途

描述一次线性任务如何按锚点执行。工作流引用一个锚点集，步骤只包含动作、输入值、可选 OCR 预期和等待策略。

### 5.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `metadata.workflow_id` | 工作流实例或草稿标识 |
| `metadata.anchor_profile` | 引用的 `anchors.yaml` 锚点集 ID |
| `metadata.author` | 工作流作者或发布来源 |
| `metadata.lifecycle_state` | 生命周期状态，如 `Draft`、`Standardized`、`Published` |
| `metadata.template_id` | 可选，发布态模板标识 |
| `metadata.template_version` | 可选，发布态模板版本 |
| `steps` | 线性步骤数组 |
| `steps[].id` | 步骤唯一标识 |
| `steps[].anchor_id` | 目标锚点 ID |
| `steps[].action` | `click`、`type`、`hotkey`、`press_enter` 之一；双击用两个连续 `click` 步骤表达 |
| `steps[].value` | 可选输入值，例如文本或快捷键 |
| `steps[].expected_text` | 可选 OCR 预期文本；非空时运行器轮询该锚点 `observe_region` |
| `steps[].match_mode` | `contains`、`equals`、`regex`、`not_empty` 或 `none` |
| `steps[].timeout_seconds` | 可选 OCR 轮询超时秒数 |
| `steps[].wait_seconds` | 可选固定等待秒数；仅在无 OCR 预期时使用 |
| `steps[].requires_confirmation` | 可选，高风险步骤执行前需人工确认 |

### 5.3 校验规则

- `metadata.anchor_profile` 必须能找到对应锚点集。
- `steps` 不得为空，v2 只支持线性顺序执行。
- 每个 `anchor_id` 必须存在于锚点集。
- `action` 必须包含在该锚点的 `supported_actions` 内。
- 当 `expected_text` 非空或 `match_mode == not_empty` 时，目标锚点必须有 `observe_region`。
- `match_mode == none` 表示不进行 OCR 判断，按 `step.wait_seconds -> anchor.default_wait_seconds -> app default 2.0s` 等待。

### 5.4 责任边界

- workflow 不声明运行结果字段；OCR 事实由运行器自动写入 `run_trace.jsonl`。
- workflow 不声明复杂判断树、流程控制或多模式识别。
- 平台若仍需要旧字段名，由平台适配器映射，不污染主契约。

## 6. `platform_adapter.yaml`

### 6.1 用途

定义 SmartAccess 与 SpecLabOS 的接口地址、认证方式、任务/模板/状态映射和重试策略。

### 6.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `base_url` | 平台 API 基地址 |
| `auth` | 认证模式和密钥引用方式 |
| `endpoint_map.health` | 健康检查接口 |
| `endpoint_map.fetch_task` | 平台任务拉取接口 |
| `endpoint_map.fetch_template` | 平台模板拉取接口 |
| `endpoint_map.publish_template` | 标准模板发布接口 |
| `endpoint_map.delete_template` | 模板版本删除接口 |
| `endpoint_map.upload_status` | 运行状态上传接口 |
| `endpoint_map.upload_logs` | 运行日志上传接口 |
| `endpoint_map.upload_trace` | 运行 trace 或步骤事实上传接口 |
| `field_map` | 本地字段到平台字段的映射 |
| `retry_policy` | 接口失败后的重试和补传规则 |

### 6.3 责任边界

- 平台适配器可以把本地 `anchor_profile` 映射为平台旧字段名，但映射只能存在于适配层。
- 平台结果上传从 `run_trace.jsonl` 提取步骤 OCR 事实。
- `fetch_task` 返回任务上下文和模板引用；`fetch_template` 根据模板 ID 与版本返回 workflow 内容，二者职责必须分离。

## 7. 设备侧 FastAPI MVP 基线接口

| 端点 | 方法 | 作用 |
| --- | --- | --- |
| `/health` | `GET` | 服务健康检查与联通性确认 |
| `/api/v1/experiment/trigger` | `POST` | 提交 `experiment_plan`，生成本地执行上下文，返回 `request_id` |
| `/api/v1/experiment/execute` | `POST` | 基于最近一次成功生成的上下文发起执行 |
| `/api/v1/experiment/status` | `GET` | 查询当前执行状态、当前步骤、最近触发时间和最新请求标识 |

调用顺序与失败语义保持不变：`execute` 必须建立在成功 `trigger` 之后；`status` 是只读轮询接口；生成失败、模板解析失败和执行失败必须写入运行轨迹。

## 8. `run_trace.jsonl`

### 8.1 用途

定义一次运行过程中按时间顺序记录的步骤级事实。它是用户、平台和审计系统读取运行结果的主来源。

### 8.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 事件时间 |
| `session_id` | 会话唯一标识 |
| `workflow_id` | 工作流标识 |
| `step_id` | 工作流步骤标识 |
| `anchor_id` | 执行锚点 ID |
| `action` | 动作类型与输入摘要 |
| `wait_strategy` | `ocr_poll` 或 `fixed_wait`，包含超时/等待秒数 |
| `expected_text` | 预期 OCR 文本，可为空 |
| `actual_text` | 实际 OCR 文本，可为空 |
| `match_mode` | 文本匹配方式 |
| `matched` | OCR 是否命中；无 OCR 判断时可为 `null` |
| `attempts` | OCR 轮询次数或执行尝试次数 |
| `elapsed_seconds` | 步骤实际耗时 |
| `screenshot_path` | 最新截图或裁剪图路径 |
| `status` | `success`、`timeout`、`failed`、`cancelled` 等 |
| `error` | 可选错误类型、消息和详情 |
| `provider_mode` | 提供者模式，用于审计真实链路或测试 stub |

### 8.3 责任边界

- `run_trace.jsonl` 采用 JSONL，方便流式写入和平台补传。
- OCR 结果自动进入 trace。
- 与模板相关的事件应能标识 `template_id`、`template_version` 和来源。

## 9. `eval_case.yaml`

### 9.1 用途

定义回归评测中的单个场景，包括输入、预期事件和通过标准。

### 9.2 核心字段

| 字段 | 说明 |
| --- | --- |
| `scenario` | 场景标识与目标 |
| `inputs` | 所需 workflow、anchors、平台配置、截图或模拟数据 |
| `expected_events` | 期望发生的动作、OCR 事实、等待策略或回传 |
| `pass_criteria` | 通过条件 |
| `fixtures` | 附件、模拟服务或基线 trace |

### 9.3 责任边界

- eval case 只定义场景和标准，不直接承载实现代码。
- 契约测试应覆盖新 `anchors.yaml`、新 `workflow.yaml` 和新 `run_trace.jsonl` 的加载与 round-trip。
- 当前 harness 包含七个关键场景，新增能力示例必须同时提供 `anchors.yaml`、`workflow.yaml`、eval case 和标准化测试。
- 已下线契约的兼容测试应随断代重构删除或重写。

## 10. 建议实现原则

- 字段命名以稳定、可读和贴近用户工作流为优先。
- 公开契约只保留锚点、线性步骤、OCR 判断和 trace 事实四类概念。
- 任何新增字段都应补充文档和样例，并同步 PRD、SPEC、README、AI memory/skill 和 demo 资产。
- 模板中心语义优先于临时运行态语义，避免把执行态字段反向滥用为模板标识。
