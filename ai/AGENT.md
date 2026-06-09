# SmartAccess Repository Agent Contract

## 目标

本文件定义仓库级 agent 的通用协作约束，用于统一产品文档维护、AI 组件落库和后续实现顺序。

## 术语

- `runtime AI`：服务 SmartAccess 产品运行时的 agent、skill、memory、harness。
- `repo AI`：服务本仓库文档和架构维护的 agent、skill、memory、harness。
- `contract`：工作流、仪器画像、平台适配、运行轨迹和评测用例等结构化接口定义。

## 工作原则

1. 文档优先：先更新 PRD、架构或契约，再进行实现设计。
2. 契约优先：涉及运行时结构的改动，必须先反映到 `docs/contracts/`。
3. 一致性优先：模块命名在 README、PRD、架构和 AI 目录中保持一致。
4. 场景驱动：优先围绕关键场景完善 memory、skill、agent、harness。
5. 可评测：新增能力时同步补充 eval harness 场景。
6. 文档同步：每次完成会影响产品行为、运行时契约、UI 语义、工作流字段或 AI 组件的改动后，必须执行 `ai/skills/repo/documentation-sync`，同步功能日志、PRD、SPEC、契约、README、memory 和相关 skill。

## 边界

### 允许

- 补充产品文档、架构文档和契约定义。
- 补充 AI 组件模板和职责说明。
- 设计新增仪器接入路径和评测基线。

### 不允许

- 在没有同步更新契约的情况下私自改变核心术语。
- 把高风险物理动作描述为默认自动执行。
- 让 repo AI 文档与 runtime AI 运行时边界混淆。

## 推荐执行顺序

1. 更新 `docs/PRD.zh-CN.md`
2. 更新 `docs/architecture/`
3. 更新 `docs/contracts/`
4. 更新 `ai/memory/`
5. 更新 `ai/skills/`
   - 重大实现或产品决策后优先运行 `ai/skills/repo/documentation-sync`
6. 更新 `ai/agents/`
7. 更新 `ai/harness/`
8. 回查 `README.md`

## 关键输入

- `README.md`
- `docs/PRD.zh-CN.md`
- `docs/architecture/*.md`
- `docs/contracts/*.md`

## 关键输出

- 一致的产品定义
- 可复用的 AI 组件模板
- 可追溯的关键场景与验收基线
