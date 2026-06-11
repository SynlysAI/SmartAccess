---
name: ui-automation-orchestrator
description: Translate SmartAccess v2 workflows into UI-level execution plans. Use whenever steps must be mapped to anchor actions, OCR polling, default waits, safety checks, or run-time execution ordering for instrument software.
---

# UI Automation Orchestrator

## 触发条件

- 需要把工作流步骤转换为 UI 执行计划。
- 需要确认动作顺序、OCR 等待、默认等待、安全检查或动作后的识别闭环。

## 输入

- `workflow.yaml`
- `anchors.yaml`
- 当前运行会话上下文

## 输出

- 可执行动作计划
- 步骤级安全检查清单
- OCR 轮询点列表
- 每个步骤的等待策略和失败处理策略

## 执行步骤

1. 解析工作流步骤和锚点集。
2. 校验每个 `anchor_id` 存在，且 `action` 在锚点 `supported_actions` 内。
3. 将 `click` 映射为点击 `action_region` 中心；双击必须由两个连续 `click` 步骤表达。
4. 将 `type` / `hotkey` / `press_enter` 映射为先聚焦锚点再输入或按键。
5. 如果步骤有 `expected_text` 或 `match_mode == not_empty`，绑定目标锚点的 `observe_region` 并创建 OCR 轮询计划。
6. 如果步骤没有 OCR 判断，解析固定等待：`step.wait_seconds -> anchor.default_wait_seconds -> app default 2.0s`。
7. 把计划交给 executor 并记录预期 trace 事件。

## 失败处理

- 如果找不到目标锚点，升级为锚点配置或恢复流程。
- 如果动作超出锚点能力，禁止继续自动执行。
- 如果需要 OCR 但锚点没有 `observe_region`，标准化失败。
- 如果停止或取消请求到达，必须中断 OCR 轮询并记录取消事实。

## 示例执行语义

- 串口调试助手 UDP 示例执行后，trace 至少应记录打开服务步骤和发送步骤的 OCR 文本。
- Windows 计算器示例执行后，最后一步必须是对 `display_result` 的 OCR 轮询，并匹配 `46`。
