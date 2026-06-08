# SmartAccess 软件总体设计

## 1. 目标

本文基于 [PRD](../PRD.zh-CN.md) 和 [Spec](../SPEC.zh-CN.md)，把 SmartAccess 从“产品与架构基线”进一步收束为可实施的软件设计。它回答四个实现问题：

- MVP 推荐采用什么样的进程与部署形态。
- 桌面端、运行时、平台适配、AI 能力之间如何分层与协作。
- 契约、数据库、文件产物和运行轨迹如何落盘与追溯。
- 研发阶段应按什么模块顺序推进，才能尽快形成可验收 MVP。

本文是研发实施蓝图，不替代 PRD、Spec 和契约文档；如果实现细节与上游文档冲突，以 PRD 和 Spec 的产品边界为准，再回到本文修订设计。

## 2. 设计原则

### 2.1 非侵入优先

- 默认通过 GUI、键鼠、截图和视觉识别与上位机交互。
- 不把厂商驱动、PLC 或安全联锁逻辑纳入 SmartAccess 责任域。

### 2.2 契约先于代码

- `workflow.yaml`、`instrument_profile.yaml`、`platform_adapter.yaml`、`run_trace.jsonl`、`eval_case.yaml` 是跨模块共享边界。
- 新能力先补契约和样例，再补界面与实现。

### 2.3 UI 与运行时解耦

- 桌面工作台负责交互和可视化，不直接承载长时间执行与平台同步。
- 运行时负责调度、执行、观察、恢复、审计和对外 API。

### 2.4 本地优先，云端可替换

- 实验执行、运行轨迹、模板副本、待补传队列必须可在断网场景下持续工作。
- AI、OCR 和视觉识别允许云端增强，但必须保留本地替代链路。

### 2.5 审计优先于智能

- AI 只负责生成建议、草稿和判断信号，不直接绕过审计链路。
- 高风险动作、人工确认、模板发布和模板回滚必须留下可追溯记录。

### 2.6 增量扩展优先

- MVP 先覆盖 Windows、单窗口、有限动作原语和基础 OCR。
- 通过 provider 接口和插件式适配，为 Linux、多窗口和多模态识别保留演进空间。

## 3. 推荐系统形态

### 3.1 部署单元

MVP 推荐把 SmartAccess 打包为一个安装包，但运行时拆成两个主进程、一个可选工作进程：

| 进程 | 主要职责 | 是否 MVP 必需 |
| --- | --- | --- |
| `smartaccess-desktop` | PyQt 工作台、页面导航、可视化监控、人工确认入口 | 是 |
| `smartaccess-runtime` | orchestrator、executor、observer、recovery、平台适配、FastAPI 服务、落盘与补传 | 是 |
| `smartaccess-ai-worker` | 长耗时 LLM/OCR/视觉任务隔离执行 | 否，预留接口 |

推荐拆分原因：

- 避免 PyQt UI 卡顿直接影响执行链路。
- 让设备侧 FastAPI 服务在桌面关闭后仍可维持最小运行能力。
- 便于后续把运行时演进为 Windows Service 或 Linux daemon。

### 3.2 逻辑通信方式

- `desktop -> runtime`：本机 `localhost` 控制 API + WebSocket/SSE 事件流。
- `runtime -> SpecLabOS`：HTTP/HTTPS 平台接口。
- `runtime -> executor/vision adapters`：进程内 service call；长耗时任务可转交 worker。
- `runtime -> local store`：SQLite + 文件系统。

### 3.3 路由分面

运行时对外暴露两类接口：

- `Edge API`：供 SpecLabOS 或运维调用，仅包含 `/health` 和实验触发/执行/状态查询接口。
- `Internal Control API`：供桌面端使用，负责工作流编辑、模板发布、运行监控、人工确认和事件订阅。

MVP 可以由同一个 FastAPI 应用承载两类路由，但必须做到逻辑分组、权限分离和审计分离。

## 4. 分层设计

### 4.1 Desktop Shell 层

职责：

- 提供统一工作台布局与页面路由。
- 展示运行状态、模板状态、仪器状态和异常上下文。
- 发起校准、生成工作流、发布模板、执行任务和人工恢复。

约束：

- 不直接改写契约文件。
- 所有读写都通过 runtime service。
- UI 展示的是 runtime 投影状态，而不是页面私有真相源。

### 4.2 Application Service 层

该层是“用例编排层”，负责把 UI 操作或平台请求转成稳定的业务流程。

建议包含：

- `WorkspaceService`
- `CalibrationService`
- `WorkflowService`
- `TemplateService`
- `RunSessionService`
- `IncidentService`
- `PlatformSyncService`
- `EvaluationService`

### 4.3 Domain 层

该层只表达领域模型、状态机和业务规则，不感知 PyQt、FastAPI 或具体第三方库。

核心聚合：

- `Workflow`
- `InstrumentProfile`
- `TemplateVersion`
- `RunSession`
- `Incident`
- `PlatformAdapterConfig`

### 4.4 Adapter 层

该层承载所有不稳定依赖：

- GUI 自动化 provider
- 截图与视觉识别 provider
- OCR provider
- LLM/规则引擎 provider
- SpecLabOS client
- SQLite repository
- 文件产物存储
- Secret provider

依赖规则：

- `desktop` 只能依赖 `application` 的 DTO 和 API。
- `application` 依赖 `domain` 与 adapter interface，不直接依赖具体 provider。
- `adapter` 可以依赖第三方库，但不得反向引用 `desktop`。

## 5. 运行时核心模块

| 模块 | 主要职责 | 输入 | 输出 |
| --- | --- | --- | --- |
| `Workflow Manager` | 管理草稿、标准化检查、参数绑定、模板装配 | 自然语言草稿、模板、平台任务 | `workflow.yaml`、本地执行上下文 |
| `Instrument Calibrator` | 维护窗口签名、锚点、ROI、安全限制 | 截图、用户标注、平台字段需求 | `instrument_profile.yaml` |
| `Automation Executor` | 执行动作原语并回写事件 | step、anchor、参数、安全限制 | 动作事件、截图、执行结果 |
| `Observer` | 采集截图并生成结构化观察结果 | ROI 配置、截图、识别规则 | observation 事件、结构化状态 |
| `Recovery Engine` | 根据异常和策略给出重试、回退或人工确认动作 | incident、run context、recovery rule | 恢复动作、升级事件 |
| `Platform Adapter` | 管理任务拉取、模板发布、状态/日志/结果同步 | platform config、domain event | 平台请求、补传任务 |
| `Run Session Manager` | 管理会话状态机、事件流和归档 | workflow、instrument profile、command | `run_trace.jsonl`、session state |
| `Artifact Store` | 统一保存截图、导出 YAML、日志、缓存副本 | 文件内容、事件引用 | 文件路径、artifact index |
| `Outbox Sync` | 负责离线缓存与补传 | 平台失败事件 | retry task、告警 |
| `AI Gateway` | 隔离 LLM、OCR、VLM 供应商差异 | prompt、截图、上下文 | 草稿、识别结果、建议 |

### 5.1 Orchestrator 的中心职责

orchestrator 不等于单一 agent，而是运行时决策中心。它需要负责：

- 建立 `RunSession`。
- 按步骤驱动 executor 与 observer。
- 根据观察结果推进、等待、分支、重试或阻塞。
- 触发 platform sync 与本地审计。
- 在异常时交给 recovery engine 决策。

### 5.2 Recovery 的边界

Recovery 只决定“怎么恢复”，不修改模板真相源。恢复动作应写入本次 session，不反向污染已发布模板；若发现模板本身有缺陷，应生成新的模板修订任务，而不是隐式热修复模板。

## 6. 推荐技术选型

| 领域 | MVP 推荐 | 设计理由 |
| --- | --- | --- |
| 桌面端 | `PyQt6` | 与 PRD 一致，适合复杂工作台和本地工具形态 |
| 运行时 API | `FastAPI + Uvicorn` | 便于同时承载设备侧接口与桌面本地控制接口 |
| 契约校验 | `Pydantic v2` + YAML loader | 统一 schema、序列化和接口校验 |
| 本地元数据 | `SQLite` | 单机稳定、易备份、事务语义清晰 |
| 文件产物 | 本地文件系统分层目录 | 适合截图、JSONL、YAML、副本缓存 |
| Windows GUI 自动化 | `pywinauto` + `pyautogui` + `mss` | 兼顾 UIA 能力、坐标操作和截图能力 |
| 视觉识别 | `OpenCV` + provider interface | 支撑模板匹配、颜色检测、规则识别 |
| OCR | 默认本地 OCR provider，建议优先评估 `PaddleOCR` | 支持离线部署，便于中英混合场景 |
| 日志 | 标准 `logging` + JSON formatter | 兼容 Python 生态和运行轨迹落盘 |
| 密钥管理 | OS keyring/凭据管理器，开发态可降级 `.env` | 避免把明文令牌写入契约文件 |

说明：

- 本节是推荐实现，不是不可变约束。
- 如果后续验证发现某个库不适配仪器上位机，优先保持 adapter interface 不变，再替换底层 provider。

## 7. 数据与存储设计

### 7.1 真相源拆分

推荐采用“双真相源”：

- `SQLite`：保存可查询的元数据、状态索引、队列和审计记录。
- `workspace 文件系统`：保存 YAML 契约、运行轨迹、截图和模板副本。

这样既能支持 UI 快速查询，也能保留可导出、可迁移、可审计的原始文件。

### 7.2 建议目录布局

```text
workspace/
|-- app.db
|-- configs/
|   |-- platform_adapter.yaml
|   `-- app_settings.yaml
|-- instruments/
|   `-- {device_id}/
|       |-- instrument_profile.yaml
|       `-- calibration_assets/
|-- workflows/
|   `-- {workflow_id}/
|       |-- draft.yaml
|       `-- revisions/
|-- templates/
|   `-- {template_id}/
|       `-- {template_version}/workflow.yaml
|-- runs/
|   `-- {session_id}/
|       |-- run_trace.jsonl
|       |-- context.json
|       |-- screenshots/
|       `-- exports/
|-- outbox/
|   `-- pending_events.jsonl
`-- logs/
    |-- runtime.log
    `-- desktop.log
```

### 7.3 SQLite 建议表

| 表 | 用途 |
| --- | --- |
| `instrument_profiles` | 仪器画像索引、状态、适用 OS、最近校准时间 |
| `workflows` | 草稿与标准化工作流索引 |
| `template_versions` | 发布态模板版本索引、来源、状态 |
| `run_sessions` | 运行会话主表，记录状态、模板来源、开始结束时间 |
| `run_steps` | 步骤执行投影，供监控页查询 |
| `incidents` | 异常、恢复动作、人工确认记录 |
| `sync_outbox` | 待补传平台事件 |
| `audit_events` | 发布、回滚、人工确认、高风险动作审计 |
| `eval_runs` | 评测执行结果 |

### 7.4 文件与数据库边界

- YAML 与 JSONL 是可交换产物，必须能脱离数据库单独归档。
- 数据库是查询索引，不应成为唯一审计来源。
- 所有文件路径都应通过 artifact index 记录，避免页面层拼路径。

## 8. API 与事件设计

### 8.1 设备侧 Edge API

保留 Spec 中定义的四个 MVP 基线接口：

- `GET /health`
- `POST /api/v1/experiment/trigger`
- `POST /api/v1/experiment/execute`
- `GET /api/v1/experiment/status`

实现要求：

- `trigger` 只负责把实验意图转为本地执行上下文。
- `execute` 只负责启动最近一次成功准备的上下文。
- `status` 只读，不承载控制动作。

### 8.2 Internal Control API

桌面端建议通过内部 API 使用运行时能力，至少覆盖以下用例：

- 仪器画像创建、编辑、校准、启停。
- 工作流草稿生成、保存、标准化检查。
- 模板发布、回滚、回拉和版本查询。
- 运行发起、暂停、继续、终止、人工确认。
- 运行事件订阅与监控数据拉取。

### 8.3 领域事件

推荐把运行过程标准化为领域事件，供 UI、日志、平台同步和补传共享：

- `workflow.standardized`
- `template.published`
- `run.created`
- `run.ready`
- `run.step.started`
- `run.step.observed`
- `run.step.succeeded`
- `run.blocked`
- `run.recovered`
- `run.completed`
- `run.failed`
- `platform.sync.failed`

领域事件先写本地，再由 `PlatformSyncService` 异步投递到 SpecLabOS；这就是 MVP 的 outbox 模式基础。

## 9. 页面与交互架构

### 9.1 统一布局

沿用 PRD 中的统一布局：

- 左侧：全局导航、运行状态、当前 workspace。
- 中央：主工作区。
- 右侧：上下文详情、AI 助手、风险提示、审计摘要。

### 9.2 五个 MVP 页面

### 工作台首页

- 任务队列卡片
- 当前设备状态
- 最近运行记录
- 待处理异常与待补传告警

### 设备接入与校准页

- 窗口发现与签名确认
- ROI/锚点标注画布
- 安全限制配置
- 平台字段映射草稿

### 工作流设计页

- 模板选择与引用
- 步骤编排器
- 参数面板
- 预检与标准化检查结果
- AI 生成与修订入口

### 模板库页

- 模板列表与筛选
- 版本历史
- 发布状态与适用仪器
- 回拉、复用、回滚入口

### 运行监控页

- 当前步骤时间线
- 最新截图与 ROI 识别结果
- 日志流
- 异常处理面板
- 人工确认与恢复动作

### 9.3 状态管理原则

- 页面不持久化核心业务状态。
- 运行时持有会话真相源，桌面端只维护 view model 和临时编辑态。
- 所有跨页面共享状态都来自 runtime 投影，不通过页面间直接传对象。

## 10. 关键流程设计

### 10.1 首次接入新仪器

1. 桌面端发起校准会话。
2. runtime 扫描窗口并创建 `InstrumentProfile` 草稿。
3. 用户标注 ROI、锚点和安全限制。
4. `CalibrationService` 生成 `instrument_profile.yaml` 与元数据索引。
5. 若存在平台字段需求，则同步生成字段映射草稿。

### 10.2 工作流从草稿到发布

1. 用户通过 AI 或手工创建 workflow draft。
2. `WorkflowService` 绑定仪器画像、ROI 和字段映射。
3. `StandardizationChecker` 校验生命周期前置条件。
4. 通过后进入 `Standardized`。
5. `TemplateService` 发布模板到 SpecLabOS，并在本地保存稳定副本。

### 10.3 平台下发任务执行

1. `PlatformAdapter` 接收任务上下文。
2. 根据 `template_id + template_version` 拉取模板。
3. `WorkflowManager` 绑定参数，生成 session context。
4. `RunSessionManager` 创建 `session_id`。
5. orchestrator 驱动 executor + observer 执行。
6. `PlatformSyncService` 异步上传状态、日志、结果和异常。

### 10.4 异常恢复

1. observer 或 executor 触发 incident。
2. `RecoveryEngine` 结合规则判断默认动作。
3. 低风险异常自动重试或回退。
4. 高风险异常进入 `Blocked`，等待人工确认。
5. 所有恢复动作写入 `run_trace.jsonl` 和 `audit_events`。

## 11. 安全、可靠性与运维设计

### 11.1 安全

- 高风险动作必须具备 `requires_manual_confirm` 标记。
- 平台认证信息只存 `secret_ref`，不写入 YAML 明文。
- Internal API 至少要求本机访问和本地令牌保护。

### 11.2 可靠性

- 平台同步采用 outbox 模式，避免回传失败阻塞本地执行。
- 模板拉取失败时回退到最近可执行副本，但必须记录命中来源。
- 运行时重启后，可从 `run_sessions` 和 `run_trace.jsonl` 恢复最后状态摘要。

### 11.3 可运维性

- `/health` 除服务状态外，应暴露运行时版本、工作区路径和执行器连通摘要。
- 运行日志与运行轨迹分离，便于排障与审计。
- 提供导出单次 session 的能力，便于离线分析。

## 12. 建议代码组织

```text
src/
`-- smartaccess/
    |-- shared/
    |   |-- contracts/
    |   |-- config/
    |   `-- events/
    |-- runtime/
    |   |-- api/
    |   |-- application/
    |   |-- domain/
    |   |-- orchestration/
    |   `-- adapters/
    |-- desktop/
    |   |-- shell/
    |   |-- pages/
    |   |-- widgets/
    |   `-- viewmodels/
    `-- bootstrap/
tests/
|-- contract/
|-- integration/
|-- e2e/
`-- fixtures/
```

建议说明：

- `shared/contracts/` 放 Pydantic schema 和 YAML serializer。
- `runtime/application/` 实现用例服务，不放第三方 API 细节。
- `runtime/adapters/` 按 `automation`、`vision`、`platform`、`storage`、`ai` 再细分。
- `desktop/viewmodels/` 只处理展示态，不承载业务规则。

## 13. MVP 实施顺序

### Phase 1：契约与基础设施

- 固化 Pydantic schema 和 YAML/JSONL 读写。
- 建立 SQLite 与 workspace 目录。
- 跑通日志、artifact store 和 outbox 基础能力。

### Phase 2：设备接入与校准

- 实现窗口发现、截图、ROI 标注、锚点保存。
- 能产出 `instrument_profile.yaml`。

### Phase 3：工作流设计与标准化

- 实现 workflow 草稿编辑、参数绑定、标准化检查。
- 能产出和回读 `workflow.yaml`。

### Phase 4：执行与观察闭环

- 实现 executor、observer、run session 状态机。
- 跑通 `run_trace.jsonl`、异常记录和人工确认。

### Phase 5：平台与模板闭环

- 实现 FastAPI MVP 四接口。
- 接入模板拉取、模板发布、状态/日志/结果回传。

### Phase 6：评测与交付

- 对齐 `ai/harness/evals/cases/` 五个关键场景。
- 完成安装包、运行时配置和运维说明。

## 14. 当前应立即落地的设计决策

在开始业务代码前，建议先确定以下 6 项：

1. `desktop + runtime` 双进程作为 MVP 默认形态。
2. 契约 schema 采用 `Pydantic v2`，文件格式保持 YAML/JSONL。
3. 本地元数据采用 `SQLite + workspace 文件系统` 双存储。
4. 平台回传使用 outbox 模式，不把网络成功作为本地执行完成前提。
5. GUI 自动化与 OCR 必须走 provider interface，避免库绑定写死。
6. 页面层只通过 runtime API 读写，不直接操作工作区文件。

## 15. 待确认项

- SpecLabOS 真实 API 字段与错误码。
- Windows GUI 自动化底层库在目标仪器上的兼容性。
- OCR 最低置信度阈值及关键读数的人工确认策略。
- FastAPI Edge API 的暴露方式，是仅内网还是需要跨机访问。
- Linux V1 阶段的自动化 provider 选型。
