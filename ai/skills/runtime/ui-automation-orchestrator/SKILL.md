---
name: ui-automation-orchestrator
description: Translate SmartAccess workflows into UI-level execution plans. Use whenever steps must be mapped to clicks, typing, waits, safety checks, or run-time execution ordering for instrument software.
---

# UI Automation Orchestrator

## 触发条件

- 需要把工作流步骤转换为 UI 执行计划。
- 需要确认动作顺序、等待条件、安全检查或动作后的识别闭环。

## 输入

- `workflow.yaml`
- `instrument_profile.yaml`
- 当前运行会话上下文

## 输出

- 可执行动作计划
- 步骤级安全检查清单
- 运行时观测点列表
- 每个关键步骤的 condition 判断方式和失败处理策略

## 执行步骤

1. 解析工作流步骤和仪器锚点。
2. 为每个步骤绑定目标控件、输入值和等待条件。
3. 根据锚点 `vision_mode` 选择 OCR、presence、template、color 或 none。
4. 在关键动作前插入安全检查，在关键动作后插入 condition 观测点。
5. `wait_until` 使用轮询条件，`screenshot_check` 使用一次性条件判断。
6. 把计划交给 executor 并记录预期事件。

## 失败处理

- 如果找不到目标锚点，升级为校准或恢复流程。
- 如果动作超出安全限制，禁止继续自动执行。
