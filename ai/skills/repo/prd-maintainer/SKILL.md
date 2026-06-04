---
name: prd-maintainer
description: Maintain the SmartAccess PRD as the source of product scope, users, scenarios, MVP/V1 boundaries, and non-functional requirements. Use whenever product behavior, scope, success metrics, or feature definitions are edited.
---

# PRD Maintainer

## 触发条件

- 需要新增、修改或审查产品需求。
- 需要同步 MVP/V1 边界、核心场景或成功指标。

## 输入

- 当前 PRD
- 架构文档
- 新的产品决策

## 输出

- 更新后的 PRD 章节
- 变更影响说明
- 需要同步的下游文档列表

## 执行步骤

1. 判断变更属于目标、范围、功能还是非功能。
2. 更新 PRD 的对应章节。
3. 检查是否影响架构、契约、README 或 AI 组件。

## 失败处理

- 若新需求与现有定位冲突，应先记录冲突再建议修改路径。
