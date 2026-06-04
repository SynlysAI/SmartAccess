# Vision Patterns Memory

- `scope`: 视觉识别模式与 ROI 观测策略。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `instrument_profile.yaml`, `run_trace.jsonl`

## 常见模式

- OCR 读数：温度、压力、电压、电流等。
- 状态文本：运行中、停止、完成、告警。
- 颜色状态：按钮启用、告警灯、区域变色。
- 模板存在性：关键图标、弹窗、标识符。

## 约束

- 模式定义必须指出适用界面和失效条件。
- 视觉判断不确定时应升级为异常或人工确认。
