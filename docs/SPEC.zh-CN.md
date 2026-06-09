# SmartAccess 技术规格说明（Spec）

## 1. 规格目标

本文把 SmartAccess 的产品需求、系统架构和运行时契约收束成面向实现的规格基线。它用于回答研发阶段最常见的四个问题：

- 系统由哪些边界清晰的模块组成。
- 这些模块围绕哪些核心领域对象协作。
- 一次任务从平台下发到本地执行、观测、回传的运行语义是什么。
- MVP 到 V1 的实现验收应以哪些契约和场景为准。

本文不替代 PRD、架构文档或契约样例。PRD 负责说明产品范围和用户价值，架构文档负责说明层次和数据流，契约文档负责定义结构化字段；本文负责把它们整理成可执行 spec。

## 2. 系统定位

SmartAccess 是运行在实验室设备侧的非侵入式仪器接入与执行层。它位于 SpecLabOS、用户和仪器上位机之间，通过桌面工作台、AI 工作流设计、UI 自动化、视觉识别和 FastAPI 适配，让没有稳定 SDK/API 的仪器也能纳入标准化实验管理。

系统默认形态：

- 桌面工作台：优先按 PyQt 桌面端规划。
- 本地执行器：负责窗口定位、输入事件、截图采集、动作执行和日志落盘。
- AI 运行时：负责工作流生成、校准辅助、状态判断和异常恢复建议。
- 平台适配层：负责与 SpecLabOS 同步任务、模板、状态、日志和结果。
- 评测体系：负责以场景化用例验证契约、模块边界和关键链路。

## 3. 架构边界

### 3.1 SmartAccess 负责

- 把自然语言或平台任务转为可执行工作流上下文。
- 管理工作流模板、仪器画像、ROI、锚点、平台字段映射和模板版本。
- 使用 UI 级动作驱动仪器上位机，而不是绕过上位机直接控制底层设备。
- 使用截图、OCR、模板匹配和规则判断执行状态。
- 记录运行轨迹、异常上下文、关键截图和平台回传结果。
- 与 SpecLabOS 进行任务拉取、模板发布、模板回拉、状态上报和结果同步。

### 3.2 SmartAccess 不负责

- 替代厂商驱动、固件、PLC 或安全联锁系统。
- 在没有审计、权限和人工确认的情况下执行高风险物理动作。
- 在 MVP 阶段实现公网多租户 SaaS、全品牌覆盖或复杂并发调度。
- 把平台任务接口和模板中心接口合并为一个模糊入口。

## 4. 核心领域对象

| 对象 | 说明 | 主契约 | 生命周期/状态 |
| --- | --- | --- | --- |
| Workflow | 实验工作流，定义步骤、前置条件、输出和重试策略 | `workflow.yaml` | `Draft -> Calibrated -> Standardized -> Published -> Ready -> Running -> Blocked -> Recovered -> Completed -> Archived` |
| Instrument Profile | 仪器画像，定义窗口签名、锚点、动作能力和安全限制 | `instrument_profile.yaml` | `Draft -> Calibrated -> Active -> Deprecated` |
| Platform Adapter | 平台适配配置，定义 API 端点、认证引用、字段映射和重试策略 | `platform_adapter.yaml` | `Draft -> Validated -> Active -> Disabled` |
| Run Session | 一次实验执行会话，绑定任务、模板、仪器画像和运行产物 | `run_trace.jsonl` | `Created -> Ready -> Running -> Blocked -> Completed/Failed -> Archived` |
| Eval Case | 回归评测场景，定义输入、预期事件和通过标准 | `eval_case.yaml` | `Draft -> Runnable -> Passing/Failing -> Retired` |
| Template Version | 发布到 SpecLabOS 的稳定模板版本 | `workflow.yaml` + 平台模板接口 | `Draft -> Standardized -> Published -> Superseded/RolledBack` |

## 5. 模块规格

### 5.1 工作台 Shell

职责：提供统一的桌面入口、导航框架、任务上下文和用户操作入口。

MVP 页面：

- 工作台首页：任务队列、设备状态、最近运行、异常提醒。
- 设备接入与校准页：窗口识别、ROI 标注、锚点配置、字段映射。
- 工作流设计页：模板选择、步骤编排、参数区、预检提示、版本说明。
- 模板库页：模板列表、版本时间线、发布状态、适用仪器、查找过滤、回滚和复用入口。
- 运行监控页：左侧步骤时间线，右侧观测/审计与日志标签页，异常恢复动作。

验收要点：页面之间共享同一任务上下文；执行中的状态变化能在运行监控页可见；高风险动作必须有明确确认点。

### 5.2 Workflow Manager

职责：管理工作流草稿、标准化检查、版本信息和发布/回拉语义。

输入：用户自然语言、已有模板、平台任务、仪器画像、字段映射。

输出：符合 `workflow.yaml` 的工作流配置。

关键规则：

- `template_id` 和 `template_version` 只用于稳定模板身份，不能用运行时 `request_id` 替代。
- `roi_bindings` 表示工作流逻辑名到仪器画像锚点的映射，多个工作流可以复用同一批锚点。
- `outputs` 表示运行后需要保留的结果 key 与观测来源，不等同于动作目标本身。
- 平台下发任务时，先解析任务上下文，再按模板 ID 和版本拉取模板内容。
- 进入 `Standardized` 前，必须完成关键 ROI/锚点、字段映射、安全限制和复用性说明。
- 发布到 SpecLabOS 后，本地保留最近可执行副本，用于平台断连时的可恢复运行。

### 5.3 Instrument Calibrator

职责：把一台仪器上位机的可见界面转换成可复用仪器画像。

输入：窗口信息、截图、用户标注、识别结果、平台字段需求。

输出：符合 `instrument_profile.yaml` 的仪器画像。

关键规则：

- 锚点必须区分动作目标和观察 ROI。
- 安全限制必须绑定到动作或参数范围，例如电压、电流、温度、启动/停止动作。
- MVP 优先覆盖单窗口、静态布局或轻微布局变化场景。
- 校准时应保存 absolute ROI 与 normalized ROI；运行时优先用 normalized ROI 按当前窗口尺寸重映射坐标。
- 固定窗口长宽比例只能作为辅助约束，不能替代锚点视觉反馈和运行前校验。
- 识别不确定时，不得把低置信结果直接升级为可执行状态。

### 5.4 Automation Executor

职责：把工作流步骤转换为 UI 级动作，并把动作结果写入运行轨迹。

动作原语（VER3 全部走真实 Win32 链路）：

- `click` / `double_click`：SetCursorPos + mouse_event 定位锚点中心点击
- `type`：SendInput + KEYEVENTF_UNICODE 逐字输入（支持 ASCII + CJK）
- `hotkey`：keybd_event 组合键（ctrl/alt/shift + 字母/enter/tab/esc）
- `press_enter`：keybd_event 发送回车键
- `wait`：time.sleep 等待指定秒数
- `wait_until`：编排器级轮询 observer 直到条件满足或超时
- `screenshot_check`：编排器级一次性观测 + 条件判断

关键规则：

- 执行前必须校验窗口存在、目标锚点可定位、参数满足安全限制。
- 每个动作必须生成可追踪事件，至少包含 `session_id`、`step_id`、动作、观察、结果和产物引用。
- `wait_until` 基于步骤级观测条件按 `poll_interval_seconds` 轮询，超时按 `timeout_seconds` 判断。
- `screenshot_check` 基于锚点识别模式执行一次观测判断。
- 所有等待时间以秒为单位；AI 生成的 ms 值自动标准化。
- `execute` 只能在成功 `trigger` 或已准备好的本地执行上下文之后发生。

### 5.5 Observer

职责：在运行中采集截图、识别状态并输出结构化观察结果。

识别方式（VER3 全部走本地 `LocalVisionProvider`）：

- **OCR**：PaddleOCR 读取 ROI 内文字，返回文本与置信度。
- **presence**：OpenCV 计算 ROI 前景像素占比，超过 `presence_threshold` 视为存在。
- **template**：OpenCV `matchTemplate` (TM_CCOEFF_NORMED) 比对基准图，分数 ≥ `template_threshold` 视为匹配。
- **color**：OpenCV 采样 ROI 均值色，计算与参考色 `color_reference_hex` 的 HSV 距离，≤ `color_tolerance` 视为匹配。
- **none**：仅作为动作目标或定位区域，不参与观测。

`AnchorDefinition.vision_config` 承载各模式的基准数据：
- `template_asset_path`：模板基准图路径
- `template_threshold`：匹配阈值（默认 0.8）
- `color_reference_hex`：颜色参考值（如 #00FF00）
- `color_tolerance`：HSV 距离容差（默认 0.1）
- `presence_threshold`：前景占比阈值（默认 0.05）

关键规则：

- 观察结果必须带来源 ROI、识别模式、置信度、时间戳和原始产物引用。
- 低置信结果进入重采样、等待或人工确认，而不是直接驱动下一步。
- 工作流步骤的 `condition` 是动作识别闭环的主要输入，orchestrator 必须在执行后判断条件是否满足。
- 关键状态变化需要写入 `run_trace.jsonl` 并可映射到平台字段。

### 5.6 Platform Adapter

职责：隔离 SmartAccess 与 SpecLabOS 的真实接口差异。

MVP 端点能力：

- 健康检查。
- 平台任务拉取。
- 模板拉取。
- 模板发布。
- 模板删除（`DELETE /smartaccess/templates/{template_id}/versions/{template_version}`）。
- 状态上传。
- 日志上传。
- 结果上传。

关键规则：

- `fetch_task` 返回任务上下文和模板引用。
- `fetch_template` 根据 `template_id + template_version` 返回模板内容。
- `publish_template` 只接收标准化后的模板。
- `delete_template` 云端删除模板版本，支持本地 `delete_version_cloud_first` 原子操作（云端成功才删本地）。
- 认证配置只保存密钥引用，不保存明文令牌。
- 平台断连时，本地缓存待补传事件和最近可执行模板副本。

### 5.7 Runtime Harness

职责：定义运行时组件装配、事件顺序、会话边界和审计要求。

关键规则：

- orchestrator 是运行时决策中心，负责在 executor、observer、recovery、platform adapter 之间协调。
- executor 只执行被授权的动作原语，不自行改变工作流语义。
- observer 只产生观察和判断，不直接执行动作。
- recovery 可以建议重试、回退、人工确认或终止，但高风险恢复必须等待确认。
- 所有组件共享同一 `session_id` 和模板来源上下文。

### 5.8 AI Runtime Knowledge Store（VER3 新增）

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

Memory 记录：稳定规则、软件特性、风险提示。
Skill 记录：可复用步骤模板、前置条件、推荐锚点和条件模式。

关键规则：

- 生成时仅检索 `approved` 项，注入到 DeepSeek system prompt。
- 生成后自动从 workflow 数据提取候选 memory/skill 进入 `pending`。
- 人工审批（approve/reject）后才从 pending 移入 approved。
- 推理面板展示本次命中的 memory/skill ID，保证可追溯。
- 提取失败不影响生成主流程。

## 6. 运行时主链路

### 6.1 本地用户发起

1. 用户在工作台选择仪器和模板，或通过 AI 生成工作流草稿。
2. Workflow Manager 校验工作流状态、仪器画像、字段映射和安全限制。
3. orchestrator 创建 run session，并装配 workflow、instrument profile、platform adapter。
4. executor 执行动作，observer 在关键节点采集状态。
5. platform adapter 同步状态、日志和结果。
6. 会话结束后归档轨迹、截图索引和模板来源。

### 6.2 SpecLabOS 下发任务

1. Platform Adapter 调用或接收任务上下文。
2. 任务上下文包含 `template_id`、`template_version`、实验参数和目标仪器。
3. SmartAccess 调用模板接口拉取指定版本模板。
4. Workflow Manager 绑定实验参数并生成本地执行上下文。
5. orchestrator 进入执行链路。
6. 执行过程持续回传状态、日志、异常和结果。

### 6.3 模板发布

1. 工作流从 `Draft` 完成校准后进入 `Calibrated`。
2. 完成字段映射、安全限制、复用性检查后进入 `Standardized`。
3. 用户或工程师填写版本说明、适用仪器和发布来源。
4. Platform Adapter 调用 `publish_template` 上传到 SpecLabOS 模板中心。
5. 发布成功后本地状态进入 `Published`，并记录平台返回的模板身份。

## 7. 设备侧 FastAPI MVP 规格

设备侧 FastAPI 基线接口用于让外部系统触发本地指令生成、发起执行和查询状态。它不是完整运行时控制面。

| 端点 | 方法 | 请求 | 响应 | 语义 |
| --- | --- | --- | --- | --- |
| `/health` | `GET` | 无 | 服务状态、时间戳、执行器连接信息 | 健康检查 |
| `/api/v1/experiment/trigger` | `POST` | `experiment_plan`、可选 `request_id` | `request_id`、生成指令、时间戳 | 生成本地执行指令 |
| `/api/v1/experiment/execute` | `POST` | 可选 `request_id` | 下发信号、执行器 ACK、时间戳 | 启动最近一次成功生成的流程 |
| `/api/v1/experiment/status` | `GET` | 无 | 当前状态、当前命令、最近触发时间、请求标识 | 只读轮询 |

状态约束：

- `trigger` 在上一轮生成仍进行中时返回冲突语义。
- `execute` 在未成功 `trigger`、生成失败或生成未完成时返回冲突语义。
- UDP/本地执行器失败返回下游执行错误，并写入运行轨迹。
- `status` 不承载暂停、恢复、终止能力。

## 8. 数据与产物规格

### 8.1 本地数据

- 工作流草稿和最近执行模板副本。
- 仪器画像和 ROI/锚点配置。
- 平台适配配置和字段映射。
- 运行轨迹 JSONL。
- 关键截图、OCR 原文、识别结果和日志文件索引。
- 待补传的平台事件队列。

### 8.2 平台回传数据

- 任务状态。
- 实验参数和阶段状态。
- 结果字段。
- 异常类型、异常上下文和恢复动作。
- 模板发布、模板拉取、版本命中和执行来源。

### 8.3 审计要求

- 每次 run session 必须有唯一 `session_id`。
- 每个步骤必须能追溯到 `workflow_id`、`step_id`、`template_id` 和 `template_version`。
- 每次人工确认、高风险动作、模板发布和模板回滚必须记录操作者、时间和说明。
- 平台断连期间不得丢失本地运行轨迹。

## 9. 异常与恢复规格

| 异常 | 典型原因 | 默认处理 | 升级条件 |
| --- | --- | --- | --- |
| WindowMissing | 上位机未打开、标题变化、权限遮挡 | 重新定位窗口 | 多次失败后人工确认 |
| AnchorMissing | 按钮或输入框找不到 | 重新截图和锚点匹配 | 仍不可信时阻塞 |
| OcrLowConfidence | ROI 模糊、遮挡、低对比度 | 重采样或等待 | 关键读数不可信时人工确认 |
| SafetyLimitViolation | 参数越界或动作风险过高 | 拒绝执行 | 只能由授权用户修改参数或模板 |
| PlatformSyncFailed | 网络断连、接口错误、认证失败 | 本地缓存后重试 | 超过阈值后告警 |
| TemplateVersionMissing | 平台无指定版本 | 拒绝执行并记录 | 需要平台或工程师处理 |
| ExecutorFailed | UDP/本地执行器失败 | 重试或终止 | 执行状态不明时必须人工确认 |

恢复动作必须写入 `run_trace.jsonl`，并保留恢复前后的观察结果。

## 10. MVP 验收规格

MVP 通过标准：

- 至少完成 1 到 3 类典型仪器的单窗口接入样例。
- 能生成并编辑 `workflow.yaml`、`instrument_profile.yaml`、`platform_adapter.yaml`。
- 能执行点击、输入、等待、截图校验和简单重试。
- 能识别至少一种关键读数和一种运行状态。
- 能发布标准工作流到 SpecLabOS 模板中心，并按模板 ID + 版本回拉执行。
- 能通过设备侧四个 FastAPI 基线接口完成健康检查、触发、执行和状态查询。
- 能生成 `run_trace.jsonl`，并包含动作、观察、结果、异常和产物引用。
- 能通过 `ai/harness/evals/cases/` 中五个关键场景的契约验收。

## 11. V1 扩展规格

V1 优先扩展：

- 多窗口、多页面和更复杂条件分支。
- Linux 上位机场景。
- 多仪器画像管理和任务队列。
- 更系统的模板审批、发布冲突处理、版本回滚和模板市场。
- 更强的视觉模式库和多模态状态识别。
- 更完整的集中监控、权限模型和审计报表。

## 12. 待确认项

- SpecLabOS 的真实任务、模板、状态、日志和结果 API 字段。
- PyQt 桌面端与 FastAPI 服务同进程还是分进程部署。
- 本地数据目录、加密策略和日志保留周期。
- OCR/视觉识别技术栈和最低置信度阈值。
- 高风险动作分级规则和人工确认 UX。
- Linux UI 自动化技术选型。
