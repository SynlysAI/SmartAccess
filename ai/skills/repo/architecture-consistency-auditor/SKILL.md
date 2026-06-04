---
name: architecture-consistency-auditor
description: Audit SmartAccess documentation and AI component directories for naming, boundary, and contract consistency. Use whenever modules are renamed, new architecture elements are introduced, or a reviewer needs to verify README/PRD/architecture/ai alignment.
---

# Architecture Consistency Auditor

## 触发条件

- 模块命名或职责变更。
- 新增契约、agent、skill、harness。
- 需要验证 README、PRD、架构文档和 AI 目录的一致性。

## 输入

- README
- PRD
- 架构文档
- `ai/` 目录

## 输出

- 一致性检查结果
- 差异清单
- 建议修复顺序

## 执行步骤

1. 对比模块命名和职责定义。
2. 检查关键场景是否能映射到 AI 组件。
3. 检查契约文档是否有样例和责任边界。

## 失败处理

- 如果发现单点定义冲突，优先回到 source of truth 修正。
