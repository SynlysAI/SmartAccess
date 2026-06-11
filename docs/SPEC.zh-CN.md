# SmartAccess 技术规格说明（Spec）

## 1. 规格目标

本文把 SmartAccess 的产品需求、系统架构和运行时契约收束成面向实现的规格基线。v2 规格以“锚点 -> 工作流 -> 执行”为主模型，回答研发阶段最常见的四个问题：

- 系统由哪些边界清晰的模块组成。
- 这些模块围绕哪些核心领域对象协作。
- 一次任务从平台下发到本地执行、OCR 观测、trace 回传的运行语义是什么。
- MVP 到 V1 的实现验收应以哪些契约和场景为准。

本文不替代 PRD、架构文档或契约样例。PRD 负责说明产品范围和用户价值，架构文档负责说明层次和数据流，契约文档负责定义结构化字段；本文负责把它们整理成可执行 spec。

## 2. 系统定位

SmartAccess 是运行在实验室设备侧的非侵入式仪器接入与执行层。它位于 SpecLabOS、用户和仪器上位机之间，通过桌面工作台、AI 工作流设计、UI 自动化、OCR 观测和 FastAPI 适配，让没有稳定 SDK/API 的仪器也能纳入标准化实验管理。

系统默认形态：

- 桌面工作台：PyQt 桌面端，四个一级页面为 `锚点`、`工作流`、`模板/平台`、`执行`。
- 本地执行器：负责窗口定位、输入事件、截图采集、动作执行和日志落盘。
- AI 运行时：负责单 prompt 工作流生成、锚点解析和异常恢复建议。
- 平台适配层：负责与 SpecLabOS 同步任务、模板、状态、日志和 trace 事实。
- 评测体系：负责以场景化用例验证契约、模块边界和关键链路。

## 3. 架构边界

### 3.1 SmartAccess 负责

- 把自然语言或平台任务转为可执行线性工作流上下文。
- 管理锚点集、工作流模板、平台字段映射和模板版本。
- 使用 UI 级动作驱动仪器上位机，而不是绕过上位机直接控制底层设备。
- 使用截图、裁剪、OCR 读取和文本匹配判断步骤结果。
- 记录运行轨迹、异常上下文、关键截图和平台回传结果。
- 与 SpecLabOS 进行任务拉取、模板发布、模板回拉、状态上报和 trace 同步。

### 3.2 SmartAccess 不负责

- 替代厂商驱动、固件、PLC 或安全联锁系统。
- 在没有审计、权限和人工确认的情况下执行高风险物理动作。
- 在 MVP 阶段实现公网多租户 SaaS、全品牌覆盖或复杂并发调度。
- 把平台任务接口和模板中心接口合并为一个模糊入口。
- 在 v2 主契约中保留复杂判断、手工结果声明或多模式识别。

## 4. 核心领域对象

| 对象 | 说明 | 主契约 | 生命周期/状态 |
| --- | --- | --- | --- |
| Anchor Profile | 锚点集，定义窗口签名、动作区域、可选 OCR 观测区域和动作能力 | `anchors.yaml` | `Draft -> Active -> Deprecated` |
| Workflow | 实验工作流，定义线性步骤、锚点引用、动作和 OCR 预期 | `workflow.yaml` | `Draft -> Standardized -> Published -> Ready -> Running -> Blocked -> Completed/Failed -> Archived` |
| Platform Adapter | 平台适配配置，定义 API 端点、认证引用、字段映射和重试策略 | `platform_adapter.yaml` | `Draft -> Validated -> Active -> Disabled` |
| Run Session | 一次实验执行会话，绑定任务、模板、锚点集和运行产物 | `run_trace.jsonl` | `Created -> Ready -> Running -> Blocked -> Completed/Failed -> Archived` |
| Eval Case | 回归评测场景，定义输入、预期事件和通过标准 | `eval_case.yaml` | `Draft -> Runnable -> Passing/Failing -> Retired` |
| Template Version | 发布到 SpecLabOS 的稳定模板版本 | `workflow.yaml` + 平台模板接口 | `Draft -> Standardized -> Published -> Superseded/RolledBack` |

## 5. 模块规格

### 5.1 工作台 Shell

职责：提供统一的桌面入口、导航框架、任务上下文和用户操作入口。

MVP 页面：

- `锚点`：窗口扫描、截图、画布、锚点表、action/observe 双区域保存。
- `工作流`：当前锚点集选择、单 prompt 输入、生成按钮、步骤表和标准化检查。
- `模板/平台`：模板列表、版本历史、发布/回拉、平台字段映射和 trace 同步状态。
- `执行`：开始/停止/取消、当前步骤、期望 OCR vs 实际 OCR、最新截图和日志。

验收要点：四页共享同一任务上下文；执行中的状态变化能在执行页可见；高风险动作必须有明确确认点；只保留四个一级入口。

### 5.2 Anchor Service

职责：管理窗口签名、锚点动作区域、可选 OCR 观测区域和坐标重映射。

输入：窗口信息、截图、用户标注、锚点表编辑。

输出：符合 `anchors.yaml` 的锚点集。

关键规则：

- 每个锚点必须有 `action_region`，可选一个 `observe_region`。
- `action_region` 和 `observe_region` 都必须同时保存 pixel 与 normalized 坐标。
- 锚点必须声明 `supported_actions` 和 `default_wait_seconds`。
- 运行时优先用 normalized 坐标按当前窗口尺寸重映射。
- 锚点集不保存运行结果、平台结果声明、视觉基准或一次性运行结果。

### 5.3 Workflow Service

职责：管理工作流草稿、标准化检查、版本信息和发布/回拉语义。

输入：用户自然语言、已有模板、平台任务、锚点集、平台字段映射。

输出：符合 `workflow.yaml` 的线性工作流配置。

关键规则：

- `template_id` 和 `template_version` 只用于稳定模板身份，不能用运行时 `request_id` 替代。
- `metadata.anchor_profile` 必须指向已存在的锚点集。
- `steps` 不得为空，v2 只支持线性顺序执行。
- 每个 `anchor_id` 必须存在，`action` 必须在锚点 `supported_actions` 内。
- 有 `expected_text` 或 `match_mode == not_empty` 时，锚点必须有 `observe_region`。
- 发布到 SpecLabOS 后，本地保留最近可执行副本，用于平台断连时的可恢复运行。

### 5.4 Automation Executor

职责：把工作流步骤转换为 UI 级动作，并把动作结果写入运行轨迹。

动作原语：

- `click`：定位到 `action_region` 中心点击；双击用两个连续 `click` 步骤表达。
- `type`：先聚焦目标锚点，再输入 `value`。
- `hotkey`：先聚焦目标锚点，再发送组合键。
- `press_enter`：先聚焦目标锚点，再发送回车。

关键规则：

- 执行前必须校验窗口存在、目标锚点可定位、动作满足锚点能力。
- `requires_confirmation` 为 true 时，必须等待人工确认。
- 每个动作必须生成可追踪事件，至少包含 `session_id`、`workflow_id`、`step_id`、`anchor_id`、动作、等待策略和产物引用。
- 固定等待按 `step.wait_seconds -> anchor.default_wait_seconds -> app default 2.0s` 解析。
- `execute` 只能在成功 `trigger` 或已准备好的本地执行上下文之后发生。

### 5.5 Observer / VisionProvider

职责：在运行中采集截图、裁剪观测区域、执行 OCR 并输出结构化文本结果。

v2 识别方式：

- **OCR**：读取 `observe_region` 内文字，返回文本、置信度、截图/裁剪图路径。
- **文本匹配**：按 `contains`、`equals`、`regex`、`not_empty`、`none` 判断是否命中。

关键规则：

- Observer 不直接执行动作。
- 低置信 OCR 结果进入重采样、等待或人工确认，而不是直接驱动下一步。
- 当步骤需要 OCR 判断时，orchestrator 按超时策略轮询 observer。
- 关键状态变化需要写入 `run_trace.jsonl` 并可映射到平台字段。
- v2 删除非 OCR 识别分支和相关 UI/测试；后续扩展必须重新走契约评审。

### 5.6 Run Service / Orchestrator

职责：建立 run session，按工作流步骤协调 executor、observer、recovery 和 platform sync。

关键规则：

- 对每步执行统一后置流程：先执行锚点动作；如果有 OCR 预期，则轮询该锚点 `observe_region`；否则固定等待。
- 轮询命中则步骤成功，超时则步骤失败并记录实际 OCR、尝试次数和截图路径。
- 停止或取消请求必须能中断 OCR 轮询。
- 所有步骤事实写入 `run_trace.jsonl`。
- 平台结果从 trace 中提取。

### 5.7 Template Service / PlatformSyncService

职责：隔离模板生命周期和 SpecLabOS 接口差异。

MVP 端点能力：

- 健康检查。
- 平台任务拉取。
- 模板拉取。
- 模板发布。
- 模板删除。
- 状态上传。
- 日志上传。
- trace 上传。

关键规则：

- `fetch_task` 返回任务上下文和模板引用。
- `fetch_template` 根据 `template_id + template_version` 返回模板内容。
- `publish_template` 只接收标准化后的简化 workflow。
- 认证配置只保存密钥引用，不保存明文令牌。
- 平台断连时，本地缓存待补传事件和最近可执行模板副本。
- 本地字段使用 `anchor_profile`；平台仍需要旧字段名时，只在适配器中映射。

### 5.8 AI Runtime Knowledge Store

职责：在工作流生成过程中持续学习，沉淀可复用知识和技能。

目录结构：`workspace/ai-runtime/`

| 目录 | 说明 |
| --- | --- |
| `episodes/` | 每次生成的完整记录（prompt、命中知识、生成结果、编辑 diff、运行结果） |
| `memory/pending/` | 候选记忆（待人工审批） |
| `memory/approved/` | 已批准记忆（参与后续生成检索） |
| `skills/pending/` | 候选技能（待人工审批） |
| `skills/approved/` | 已批准技能（参与后续生成检索） |
| `index.json` | 可搜索索引 |

关键规则：

- 生成时仅检索 `approved` 项，注入到 system prompt。
- 生成后自动从简化 workflow 数据提取候选 memory/skill 进入 `pending`。
- system prompt 禁止输出旧字段。
- 人工审批后才从 pending 移入 approved。
- 提取失败不影响生成主流程。

## 6. 运行时主链路

### 6.1 本地用户发起

1. 用户在锚点页选择或创建锚点集。
2. 用户在工作流页手工编辑或通过 AI 生成工作流草稿。
3. Workflow Service 校验锚点集、步骤、动作能力和 OCR 观测区域。
4. Run Service 创建 run session，并装配 workflow、anchors、platform adapter。
5. orchestrator 执行动作和 OCR/等待后置流程。
6. PlatformSyncService 同步状态、日志和 trace 事实。
7. 会话结束后归档轨迹、截图索引和模板来源。

### 6.2 SpecLabOS 下发任务

1. PlatformSyncService 调用或接收任务上下文。
2. 任务上下文包含 `template_id`、`template_version`、实验参数和目标锚点集。
3. SmartAccess 调用模板接口拉取指定版本模板。
4. Workflow Service 绑定实验参数并生成本地执行上下文。
5. orchestrator 进入执行链路。
6. 执行过程持续回传状态、日志、异常和 trace。

### 6.3 模板发布

1. 工作流从 `Draft` 完成标准化检查。
2. 用户或工程师填写版本说明、适用锚点集和发布来源。
3. Template Service 调用 `publish_template` 上传到 SpecLabOS 模板中心。
4. 发布成功后本地状态进入 `Published`，并记录平台返回的模板身份。

## 7. 设备侧 FastAPI MVP 规格

设备侧 FastAPI 基线接口用于让外部系统触发本地指令生成、发起执行和查询状态。它不是完整运行时控制面。

| 端点 | 方法 | 请求 | 响应 | 语义 |
| --- | --- | --- | --- | --- |
| `/health` | `GET` | 无 | 服务状态、时间戳、执行器连接信息 | 健康检查 |
| `/api/v1/experiment/trigger` | `POST` | `experiment_plan`、可选 `request_id` | `request_id`、生成上下文、时间戳 | 生成本地执行上下文 |
| `/api/v1/experiment/execute` | `POST` | 可选 `request_id` | 下发信号、执行器 ACK、时间戳 | 启动最近一次成功生成的流程 |
| `/api/v1/experiment/status` | `GET` | 无 | 当前状态、当前步骤、最近触发时间、请求标识 | 只读轮询 |

状态约束：

- `trigger` 在上一轮生成仍进行中时返回冲突语义。
- `execute` 在未成功 `trigger`、生成失败或生成未完成时返回冲突语义。
- 下游执行器失败返回执行错误，并写入运行轨迹。
- `status` 不承载暂停、恢复、终止能力。

## 8. 数据与产物规格

### 8.1 本地数据

- 锚点集和最近执行模板副本。
- 工作流草稿。
- 平台适配配置和字段映射。
- 运行轨迹 JSONL。
- 关键截图、OCR 原文、匹配结果和日志文件索引。
- 待补传的平台事件队列。

### 8.2 平台回传数据

- 任务状态。
- 实验参数和阶段状态。
- 步骤级 OCR 事实。
- 异常类型、异常上下文和恢复动作。
- 模板发布、模板拉取、版本命中和执行来源。

### 8.3 审计要求

- 每次 run session 必须有唯一 `session_id`。
- 每个步骤必须能追溯到 `workflow_id`、`step_id`、`anchor_id`、`template_id` 和 `template_version`。
- 每次人工确认、高风险动作、模板发布和模板回滚必须记录操作者、时间和说明。
- 平台断连期间不得丢失本地运行轨迹。

## 9. 异常与恢复规格

| 异常 | 典型原因 | 默认处理 | 升级条件 |
| --- | --- | --- | --- |
| WindowMissing | 上位机未打开、标题变化、权限遮挡 | 重新定位窗口 | 多次失败后人工确认 |
| AnchorMissing | 按钮或输入框找不到 | 重新截图和坐标重映射 | 仍不可信时阻塞 |
| OcrTimeout | 期望文本未在超时内出现 | 记录实际 OCR 并失败 | 关键步骤需人工确认 |
| OcrLowConfidence | ROI 模糊、遮挡、低对比度 | 重采样或等待 | 关键读数不可信时人工确认 |
| ConfirmationRequired | 步骤标记需要人工确认 | 阻塞等待确认 | 用户拒绝则取消 |
| PlatformSyncFailed | 网络断连、接口错误、认证失败 | 本地缓存后重试 | 超过阈值后告警 |
| TemplateVersionMissing | 平台无指定版本 | 拒绝执行并记录 | 需要平台或工程师处理 |
| ExecutorFailed | 本地执行器失败 | 重试或终止 | 执行状态不明时必须人工确认 |

恢复动作必须写入 `run_trace.jsonl`，并保留恢复前后的观察结果。

## 10. MVP 验收规格

MVP 通过标准：

- 至少完成 1 到 3 类典型仪器的单窗口接入样例。
- 能生成并编辑 `anchors.yaml`、`workflow.yaml`、`platform_adapter.yaml`。
- 能执行点击、双击、输入、快捷键、回车和默认等待。
- 能完成 OCR 命中成功、OCR 超时失败、无观测区域默认等待三类运行路径。
- 能发布标准工作流到 SpecLabOS 模板中心，并按模板 ID + 版本回拉执行。
- 能通过设备侧四个 FastAPI 基线接口完成健康检查、触发、执行和状态查询。
- 能生成 `run_trace.jsonl`，并包含动作、等待策略、期望 OCR、实际 OCR、匹配结果、截图路径、异常和产物引用。
- 能通过 `ai/harness/evals/cases/` 中七个关键场景的契约验收，其中包含串口调试助手 UDP 打开/发送和 Windows 计算器 `12+34=46` OCR 证明。

示例验收资产：

- `docs/contracts/examples/serial_debug_assistant_udp/`：串口调试助手 UDP 服务打开、消息发送和收发日志 OCR。
- `docs/contracts/examples/windows_calculator/`：Windows 计算器表达式输入、回车计算和结果区 OCR。

## 11. V1 扩展规格

V1 优先扩展：

- 多窗口、多页面和更复杂流程控制。
- Linux 上位机场景。
- 批量锚点集管理和任务队列。
- 更系统的模板审批、发布冲突处理、版本回滚和模板市场。
- 更完整的集中监控、权限模型和审计报表。
- 在 v2 主模型稳定后，再评估多模态状态识别扩展。

## 12. 待确认项

- SpecLabOS 的真实任务、模板、状态、日志和 trace API 字段。
- PyQt 桌面端与 FastAPI 服务同进程还是分进程部署。
- 本地数据目录、加密策略和日志保留周期。
- OCR 技术栈、最低置信度阈值和轮询间隔默认值。
- 高风险动作分级规则和人工确认 UX。
- Linux UI 自动化技术选型。
