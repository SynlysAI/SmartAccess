# SmartAccess

SmartAccess 是一个面向科学仪器上位机软件的非侵入式实验接入与执行助手。它通过 `AI Agent + UI 自动化 + 视觉识别 + 平台适配` 的组合，把原本分散、手工、异构的实验操作流程沉淀为可执行、可回放、可审计的标准工作流。

当前仓库定位为`产品与架构基线`，用于统一产品定义、AI 组件边界、关键契约和后续研发入口；它不是已经完成的业务代码仓库。

## 产品定位

### 是什么

- 一个运行在实验室侧的桌面执行层，默认按 `PyQt` 桌面端规划。
- 一个连接 SpecLabOS 的非侵入式仪器接入方案，核心依赖 UI 模拟操作、截图感知和结构化数据回传。
- 一个把“仪器接入、工作流设计、状态感知、异常恢复、数据同步”串成闭环的 AI 运行时。

### 不是什么

- 不是直接替代仪器原生控制软件的驱动层或固件层。
- 不是默认要求每台仪器开放 SDK、串口协议或私有 API 的深度集成方案。
- 不是现阶段就承诺支持全部品牌、全部系统、全部自动化能力的通用控制平台。

## 核心价值

- 非侵入式接入：尽量不改动现有上位机软件和实验流程。
- AI 辅助配置：通过引导式对话生成标准工作流和平台映射。
- 视觉感知补齐接口缺口：当仪器没有开放 API 时，仍可通过 ROI/OCR/截图比对感知状态。
- 数据统一回传：把状态、参数、日志和异常统一上传到 SpecLabOS。
- 可追溯和可扩展：以模板、契约和评测用例支撑后续仪器扩展。

## 核心文档

- [产品需求文档](docs/PRD.zh-CN.md)
- [系统架构总览](docs/architecture/system-overview.md)
- [AI 组件设计](docs/architecture/ai-components.md)
- [关键契约与样例](docs/contracts/interfaces.md)
- [仓库级 Agent 协作约束](ai/AGENT.md)

## 仓库结构

```text
.
|-- README.md
|-- SmartAccess.png
|-- docs/
|   |-- PRD.zh-CN.md
|   |-- architecture/
|   `-- contracts/
`-- ai/
    |-- AGENT.md
    |-- memory/
    |-- skills/
    |-- agents/
    `-- harness/
```

### `docs/`

- `PRD.zh-CN.md`：SmartAccess 的规范 PRD 主文件。
- `architecture/system-overview.md`：把架构图转换为可实现的文字说明。
- `architecture/ai-components.md`：定义 memory、skill、agent、harness 的边界和协作方式。
- `contracts/interfaces.md`：沉淀运行时契约、字段含义和最小样例。

### `ai/`

- `memory/`：沉淀稳定知识和长期上下文，分为 `repo` 与 `product` 两类。
- `skills/`：沉淀可复用执行能力，分为 `runtime` 与 `repo` 两类。
- `agents/`：定义运行时代理和仓库协作代理的职责边界。
- `harness/`：定义运行时装配方式与回归评测基线。

## 体系总览

![SmartAccess 架构总览](docs/refer/SmartAccess.png)

上图中的关键关系已经在 [系统架构总览](docs/architecture/system-overview.md) 中文字化，重点包括：

- `Action Flow`：用户意图经 AI Agent 生成工作流，再驱动 UI 自动化执行。
- `Data Flow`：上位机状态、识别结果、运行日志、实验参数回流到 SmartAccess 和 SpecLabOS。
- `API Flow`：SmartAccess 通过 FastAPI 适配层与 SpecLabOS 双向同步任务、参数和执行状态。

## AI 组件分层

### 产品运行时 AI

- `memory/product/`：工作流原语、仪器画像、视觉模式、恢复规则。
- `skills/runtime/`：工作流设计、UI 编排、视觉校准、平台映射、异常恢复。
- `agents/runtime/`：orchestrator、executor、observer、recovery。
- `harness/runtime/`：运行时装配、事件总线、会话边界、审计约束。

### 仓库协作 AI

- `memory/repo/`：项目背景、术语、路线图。
- `skills/repo/`：PRD 维护、架构一致性检查、README 维护。
- `agents/repo/`：product-analyst、technical-writer、architecture-steward。
- `harness/evals/`：关键场景回归评测和契约验收。

## 新增一个仪器接入的最小步骤

1. 在 `docs/contracts/` 明确该仪器的 `instrument_profile`、平台字段映射和预期输出。
2. 在 `ai/memory/product/` 补充仪器画像、界面锚点、状态识别模式和安全限制。
3. 在 `ai/skills/runtime/` 选择或新增对应的工作流设计、视觉校准、平台映射技能。
4. 在 `ai/agents/runtime/` 明确 orchestrator、executor、observer、recovery 的职责分配。
5. 在 `ai/harness/evals/cases/` 新增回归用例，覆盖首次接入、执行、异常和回传。

## 推荐开发顺序

1. 先固化契约：工作流、仪器画像、平台适配、运行轨迹、评测用例。
2. 再实现桌面端基础能力：截图采集、窗口锚点定位、输入事件执行、日志落盘。
3. 接着实现 AI 运行时编排：工作流生成、校准会话、状态观察和恢复策略。
4. 最后补平台闭环：FastAPI 适配、状态上报、模板管理、评测自动化。

## 当前默认假设

- MVP 以 `Windows` 上位机场景为主，`Linux` 支持进入 V1。
- 部署优先考虑实验室内网，可接外部模型，但必须保留本地替代策略。
- SpecLabOS 的真实 API 细节尚未落库，因此平台契约先以占位结构定义。
- 研发工作以“文档先行、契约先行、评测先行”为原则。
