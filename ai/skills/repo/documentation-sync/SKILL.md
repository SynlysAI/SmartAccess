---
name: documentation-sync
description: Keep SmartAccess product docs, repo memory, skills, changelog, and README aligned after every meaningful implementation or product decision.
---

# Documentation Sync

## 触发条件

- 完成产品功能、运行时契约、UI 行为或工作流语义改动。
- 修改 `workflow.yaml`、`instrument_profile.yaml`、`run_trace.jsonl` 等契约字段或运行语义。
- 新增、删除或重命名核心页面、服务、AI 组件、skill、agent、memory。
- 用户要求“沉淀到文档 / 更新日志 / memory / skill / PRD / README”。

## 输入

- 当前变更 diff 或实现摘要。
- `docs/PRD.zh-CN.md`
- `docs/SPEC.zh-CN.md`
- `docs/contracts/interfaces.md`
- `README.md`
- `docs/CHANGELOG.zh-CN.md`
- `ai/memory/**`
- `ai/skills/**`
- 必要时读取 `ai/AGENT.md` 和 `docs/architecture/ai-components.md`。

## 输出

- 更新后的功能更新日志。
- 与改动一致的 PRD、SPEC、契约和 README。
- 更新后的项目级 memory 与相关 runtime/repo skill。
- 需要后续补充的架构、测试或验收项清单。

## 执行步骤

1. 先判断变更类型：产品行为、技术规格、契约字段、运行时语义、文档流程或 AI 组件。
2. 更新 `docs/CHANGELOG.zh-CN.md`，记录日期、版本、功能点、验证结果和限制。
3. 如果影响用户可见行为，更新 `docs/PRD.zh-CN.md` 的产品范围、功能需求、界面框架或非功能要求。
4. 如果影响实现语义，更新 `docs/SPEC.zh-CN.md` 的模块规格、运行链路或验收规则。
5. 如果影响结构化字段或样例语义，更新 `docs/contracts/interfaces.md`，必要时同步 `docs/contracts/examples/`。
6. 如果新增文档、入口流程或核心能力，更新 `README.md` 的核心文档、仓库结构、开发顺序或当前默认假设。
7. 更新 `ai/memory/` 中稳定知识，特别是 `repo/milestones.md`、`product/workflow-primitives.md`、`product/vision-patterns.md`。
8. 更新相关 `ai/skills/`，让下一次同类改动知道如何复用新规则。
9. 检查文档之间是否出现命名冲突，如“上下文/工具栏”、`roi_bindings` 语义、模板回滚语义、vision mode 命名。
10. 在最终说明中列出已更新文档和未执行/失败的验证。

## 失败处理

- 如果 PRD 和 SPEC 对同一能力描述冲突，优先按 PRD 明确产品边界，再回写 SPEC 的实现语义。
- 如果代码已实现但契约未表达，先补契约说明，再补 README 或 skill。
- 如果变更仅是临时调试或一次性修复，不写入长期 memory；只写 changelog 或本次任务说明。
- 如果用户要求自动化“每次改动都更新文档”，应将本 skill 作为项目级流程约束，并在 `ai/AGENT.md` 与 README 中引用。
