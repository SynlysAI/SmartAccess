---
name: ui-automation-orchestrator
description: Translate SmartAccess workflows into UI execution plans. Use when mapping steps to anchors, pre-action visual checks, OCR steps, post-action waits, confirmations, safety checks, or runtime ordering.
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
2. 校验非 `wait` 步骤的 `anchor_id` 和 `view_id` 存在。
3. 将 `click` 映射为点击 `action_region` 中心；双击必须由两个连续 `click` 步骤表达。
4. 将 `type` / `hotkey` / `press_enter` 映射为先聚焦锚点再输入或按键。
5. 动作执行前按锚点 `precheck` 完成图像、文字或组合校验，再处理步骤人工确认。
6. `ocr` 必须是独立步骤，使用锚点 `action_region` 轮询文字条件；默认超时 `10.0s`、轮询间隔 `0.5s`，允许按步骤配置。
7. 非 `wait` 步骤成功后等待 `step.wait_seconds`；缺省为 `1.0s`，显式 `0` 表示不等待。
8. `wait` 步骤的 `wait_seconds` 表示等待时长，不绑定视图或锚点。
9. 把计划交给 executor 并记录预期 trace 事件。

## 失败处理

- 如果找不到目标锚点，升级为锚点配置或恢复流程。
- 如果锚点执行前校验失败，禁止执行动作。
- 如果 OCR 步骤缺少锚点，标准化失败。
- 如果停止或取消请求到达，必须中断 OCR 轮询并记录取消事实。

## 示例执行语义

- 串口调试助手 UDP 示例执行后，trace 至少应记录打开服务步骤和发送步骤的 OCR 文本。
- Windows 计算器示例执行后，最后一步必须是对 `display_result` 的 OCR 轮询，并匹配 `46`。
