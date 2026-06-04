# Workflow Primitives Memory

- `scope`: SmartAccess 运行时允许使用的基础工作流原语。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `workflow.yaml`, `run_trace.jsonl`

## 原语集合

- `click`
- `double_click`
- `type`
- `hotkey`
- `wait_until`
- `capture`
- `branch`
- `loop`
- `pause_for_confirmation`

## 设计要求

- 每个原语都必须可落到可审计事件。
- 高风险原语必须支持人工确认。
- 原语扩展前先更新本文件和 `workflow.yaml` 文档。
