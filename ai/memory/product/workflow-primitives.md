# Workflow Primitives Memory

- `scope`: SmartAccess 运行时允许使用的基础工作流原语。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-09
- `related_contracts`: `workflow.yaml`, `run_trace.jsonl`

## 原语集合

- `click`
- `double_click`
- `type`
- `hotkey`
- `wait`
- `wait_until`
- `screenshot_check`
- `capture`
- `branch`
- `loop`
- `pause_for_confirmation`

## 设计要求

- 每个原语都必须可落到可审计事件。
- `wait_until` 必须绑定观测条件并轮询到条件满足或超时。
- `screenshot_check` 必须读取指定观测源并执行一次条件判断。
- 高风险原语必须支持人工确认。
- 原语扩展前先更新本文件和 `workflow.yaml` 文档。

## 绑定与输出语义

- `roi_bindings` 是“工作流逻辑名 -> 仪器锚点 ID”，用于让多个工作流复用同一套校准锚点。
- `outputs` 是“结果 key -> 观测来源”，用于声明运行结束或关键节点需要保留的结构化结果。
- 步骤级 `condition` 是动作识别闭环入口，应包含 source/mode/operator/expected/timeout 等字段。
