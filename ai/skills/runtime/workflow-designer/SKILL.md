---
name: workflow-designer
description: Generate or refine SmartAccess experiment workflows from user intent, instrument context, and platform requirements. Use whenever the task involves turning experiment steps into `workflow.yaml`, reviewing workflow structure, or checking preconditions, outputs, and retry rules.
---

# Workflow Designer

## 触发条件

- 用户要求生成、修改或审查实验工作流。
- 需要把自然语言步骤转为 `workflow.yaml`。
- 需要补充前置条件、ROI 绑定、步骤级观测条件、输出字段或重试策略。

## 输入

- 用户实验目标和步骤描述
- `instrument_profile.yaml`
- 已有模板或平台字段要求

## 输出

- 结构化工作流草稿
- `roi_bindings` 语义说明，即工作流逻辑名到仪器锚点 ID 的映射
- `outputs` 语义说明，即结果 key 到观测来源的映射
- 步骤级 `condition`，用于动作后观测和判断
- 需要人工确认的风险点
- 缺失信息清单

## 执行步骤

1. 读取工作流原语和仪器画像约束。
2. 拆分实验步骤，映射到标准原语。
3. 补齐 `metadata`、`preconditions`、`roi_bindings`、`steps.condition`、`outputs` 和 `retry_policy`。
4. 确认 `roi_bindings` 左侧使用业务语义别名，右侧使用已校准锚点 ID。
5. 为 `wait_until`、`screenshot_check` 和关键动作补充 source/mode/operator/expected/timeout。
6. 标出高风险步骤和需要人工确认的节点。

## 提示词与界面文案规则

- 面向用户的提示、按钮和说明必须使用产品化表达，避免出现开发者口吻、调试口吻或内部实现细节。
- 生成工作流时，输出必须严格匹配 SmartAccess `WorkflowContract`；步骤使用 `target` 和 `value`，不要使用未定义字段替代。
- Provider 名称只在配置、状态或错误定位场景出现；普通流程说明使用“AI 助手”“生成工作流草稿”等稳定表达。
- 示例应贴近真实 SmartAccess 操作：选择设备、引用锚点、编排动作、配置观测条件、保存输出项。
- 涉及等待、轮询和截图校验时，时间单位统一为秒，条件字段优先使用 `source/mode/operator/expected/timeout_seconds/poll_interval_seconds`。

## 失败处理

- 如果步骤无法映射到原语，明确指出缺口而不是臆造动作。
- 如果仪器画像缺失，要求先完成接入或校准。
