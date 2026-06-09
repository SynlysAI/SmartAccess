# SmartAccess AI 组件设计

## 1. 设计目标

SmartAccess 的 AI 组件分为两层：

- `产品运行时 AI`：服务真实的实验工作流设计、执行、观察和恢复。
- `仓库协作 AI`：服务产品文档、架构约束和研发协作。

本文定义四类组件：`memory`、`skill`、`agent`、`harness`，以及它们的边界、目录和协作方式。

## 2. 目录约定

```text
ai/
|-- AGENT.md
|-- memory/
|   |-- repo/
|   `-- product/
|-- skills/
|   |-- repo/
|   `-- runtime/
|-- agents/
|   |-- repo/
|   `-- runtime/
`-- harness/
    |-- runtime/
    `-- evals/
```

## 3. 组件职责

### 3.1 Memory

用途：保存稳定知识、设计约束和长期上下文，不直接执行动作。

统一模板：

- `scope`：这份 memory 覆盖什么边界。
- `source_of_truth`：它依赖哪些主文档或主契约。
- `last_reviewed`：最近审阅日期。
- `related_contracts`：关联的契约与样例。

分类：

- `memory/repo/`：项目背景、术语、路线图。
- `memory/product/`：工作流原语、仪器画像、视觉模式、恢复规则。

### 3.2 Skill

用途：把可复用能力沉淀为带触发条件和操作步骤的执行单元。

统一结构：

- frontmatter：`name`、`description`
- 触发条件
- 输入
- 输出
- 执行步骤
- 失败处理

分类：

- `skills/runtime/`：服务 SmartAccess 运行时。
- `skills/repo/`：服务仓库协作与文档维护。

### 3.3 Agent

用途：承担一个明确目标，对多个 memory、skill、harness 进行编排。

统一结构：

- 目标
- 输入
- 输出
- 禁止事项
- 协作关系

分类：

- `agents/runtime/`：orchestrator、executor、observer、recovery。
- `agents/repo/`：product-analyst、technical-writer、architecture-steward。

### 3.4 Harness

用途：定义组件如何被装配、运行和评测。

分类：

- `harness/runtime/`：定义运行时装配、事件流、会话边界和审计要求。
- `harness/evals/`：定义回归用例、评测维度和验收门槛。

## 4. 运行时调用关系

### 4.1 主链路

1. orchestrator 读取 `workflow.yaml`、`instrument_profile.yaml`、`platform_adapter.yaml`。
2. orchestrator 根据任务阶段选择 runtime skill。
3. executor 执行动作原语并将结果写入 `run_trace.jsonl`。
4. observer 读取截图与 ROI 配置，输出结构化状态。
5. recovery agent 在异常时接管，应用恢复 skill 和恢复规则 memory。
6. runtime harness 负责会话装配、事件顺序、审计边界和组件注入。

### 4.2 仓库协作链路

1. product-analyst 读取 PRD、路线图和契约。
2. technical-writer 维护 README、PRD 和用户可读文档。
3. architecture-steward 校验命名、目录、契约和 AI 组件一致性。
4. eval harness 以场景用例验证文档和组件设计是否覆盖关键链路。

## 5. 场景到组件映射

| 场景 | Memory | Skill | Agent | Harness |
| --- | --- | --- | --- | --- |
| 首次仪器接入 | `instrument-archetypes` | `vision-calibrator`、`platform-mapper` | orchestrator、observer | runtime、eval case 01 |
| 工作流生成 | `workflow-primitives` | `workflow-designer` | orchestrator | runtime、eval case 02 |
| 执行中状态识别 | `vision-patterns` | `ui-automation-orchestrator`、`vision-calibrator` | executor、observer | runtime、eval case 03 |
| 异常恢复 | `failure-recovery-rules` | `incident-recovery` | recovery、orchestrator | runtime、eval case 04 |
| 平台数据回传 | `project-context`、`workflow-primitives` | `platform-mapper` | orchestrator | runtime、eval case 05 |
| 文档同步 | `project-context`、`milestones` | `documentation-sync`、`prd-maintainer`、`readme-maintainer` | technical-writer、architecture-steward | eval harness / 文档审查 |

## 6. 组件验收要求

### 6.1 Memory

- 能说明适用边界。
- 能指向主文档与主契约。
- 能为下游 skill/agent 提供稳定术语和规则。

### 6.2 Skill

- 触发条件清晰。
- 输入输出可核查。
- 失败处理不与其他 skill 冲突。

### 6.3 Agent

- 目标单一。
- 禁止事项明确。
- 知道什么时候调用什么 skill，什么时候升级异常。

### 6.4 Harness

- 运行时 harness 能说明组件如何装配。
- eval harness 能给出可复现的场景、指标和通过门槛。

## 7. 与契约的关系

AI 组件必须围绕以下运行时契约协作：

- `workflow.yaml`
- `instrument_profile.yaml`
- `platform_adapter.yaml`
- `run_trace.jsonl`
- `eval_case.yaml`

字段定义与样例见 [../contracts/interfaces.md](../contracts/interfaces.md)。

## 8. 对实现者的要求

- 不要先写不可复用脚本再补文档；先更新契约和 AI 组件模板。
- 新增仪器时，优先补 `memory/product/` 和 `harness/evals/cases/`。
- 修改模块命名时，必须同步 PRD、README、架构文档和相关 skill/agent。
- 完成功能实现或产品决策后，必须执行 `ai/skills/repo/documentation-sync`，把变更沉淀到功能日志、PRD、SPEC、契约、README、memory 和相关 skill。
