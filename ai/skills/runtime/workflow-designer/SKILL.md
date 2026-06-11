---
name: workflow-designer
description: Generate or refine SmartAccess v2 experiment workflows from user intent, selected anchor profile, and platform requirements. Use whenever the task involves turning experiment steps into simplified `workflow.yaml`, reviewing workflow structure, or checking anchor/action/OCR wait rules.
---

# Workflow Designer

## 触发条件

- 用户要求生成、修改或审查实验工作流。
- 需要把自然语言步骤转为简化 `workflow.yaml`。
- 需要检查锚点、动作能力、OCR 预期、等待策略或人工确认点。

## 输入

- 用户实验目标和步骤描述。
- 当前选择的 `anchors.yaml`。
- 已有模板或平台任务要求。

## 输出

- 结构化工作流草稿。
- 每个步骤的 `anchor_id`、`action`、`value?`、`expected_text?`、`match_mode`、等待字段和确认字段。
- 需要人工确认的风险点。
- 缺失信息清单。

## 执行步骤

1. 读取工作流原语和锚点集约束。
2. 把自然语言拆成线性 step intent。
3. 将每个 intent 解析到一个已存在锚点和一个锚点支持的动作。
4. 若用户期待动作后出现文字，补充 `expected_text`、`match_mode` 和 `timeout_seconds`。
5. 若不需要 OCR 判断，设置 `match_mode: none`，并按需补充 `wait_seconds`。
6. 标出高风险步骤和需要人工确认的节点。
7. 输出前检查不包含任何旧字段。

## 提示词与界面文案规则

- 面向用户的提示、按钮和说明必须使用产品化表达，避免出现开发者口吻、调试口吻或内部实现细节。
- 生成工作流时，输出必须严格匹配 SmartAccess v2 `WorkflowContract`；步骤使用 `anchor_id` 和 `action`，不要使用 `target` 或未定义字段替代。
- 禁止输出复杂绑定、手工结果声明、复杂判断对象或多模式识别字段。
- Provider 名称只在配置、状态或错误定位场景出现；普通流程说明使用“AI 助手”“生成工作流草稿”等稳定表达。
- 示例应贴近真实 SmartAccess 操作：选择锚点集、引用锚点、编排动作、配置 OCR 预期、保存工作流。
- 涉及等待和轮询时，时间单位统一为秒。

## 失败处理

- 如果步骤无法映射到锚点或动作能力，明确指出缺口而不是臆造动作。
- 如果锚点集缺失，要求先完成锚点配置。
- 如果步骤需要 OCR 预期但目标锚点没有 `observe_region`，要求补充观测区域或移除 OCR 预期。

## 已验证能力样例

- 串口调试助手 UDP：使用 `serial_debug_assistant_udp` 锚点集，步骤覆盖选择 UDP、设置本地端口、打开服务、输入发送内容、OCR 校验日志包含发送文本。
- Windows 计算器：使用 `windows_calculator` 锚点集，步骤输入 `12+34`、回车，并用结果显示区 OCR 校验 `46`。
