---
name: ui-automation-orchestrator
description: Translate SmartAccess workflows into UI-level execution plans. Use whenever steps must be mapped to clicks, typing, waits, safety checks, or run-time execution ordering for instrument software.
---

# UI Automation Orchestrator

## 触发条件

- 需要把工作流步骤转换为 UI 执行计划。
- 需要确认动作顺序、等待条件或安全检查。

## 输入

- `workflow.yaml`
- `instrument_profile.yaml`
- 当前运行会话上下文

## 输出

- 可执行动作计划
- 步骤级安全检查清单
- 运行时观测点列表

## 执行步骤

1. 解析工作流步骤和仪器锚点。
2. 为每个步骤绑定目标控件、输入值和等待条件。
3. 在关键动作前插入安全检查和观测点。
4. 把计划交给 executor 并记录预期事件。

## 失败处理

- 如果找不到目标锚点，升级为校准或恢复流程。
- 如果动作超出安全限制，禁止继续自动执行。
