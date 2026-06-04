# Failure Recovery Rules Memory

- `scope`: 运行异常分类与恢复策略。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `run_trace.jsonl`, `eval_case.yaml`

## 异常分类

- `ui_target_missing`
- `ocr_untrusted`
- `window_focus_lost`
- `platform_sync_failed`
- `unsafe_state_detected`

## 恢复策略

- `retry_same_step`
- `relocate_window`
- `rebind_roi`
- `pause_for_confirmation`
- `abort_session`

## 恢复要求

- 恢复动作必须写入 `run_trace.jsonl`。
- 超过阈值的异常必须升级为人工确认或终止。
