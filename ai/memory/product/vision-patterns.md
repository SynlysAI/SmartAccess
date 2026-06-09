# Vision Patterns Memory

- `scope`: 视觉识别模式与 ROI 观测策略。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`
- `last_reviewed`: 2026-06-09
- `related_contracts`: `instrument_profile.yaml`, `run_trace.jsonl`

## 常见模式

- OCR：动态文本、数值、状态文案、消息内容。
- presence：元素、弹窗、结果行或按钮区域是否出现。
- template：稳定图标、按钮形态、选中态或像素模板是否匹配。
- color：按钮启用/禁用、告警灯、区域状态色。
- none：只作为动作目标或定位区域，不参与观测。

## 坐标与鲁棒性

- 校准阶段应同时保存 absolute ROI 与 normalized ROI。
- 运行时优先用 normalized ROI 按当前窗口尺寸重映射坐标。
- 固定窗口长宽比例只能降低失败概率，不能替代视觉反馈。
- 对关键点击或读取锚点，应逐步补充 template/pixel block 反馈和 match score。

## 约束

- 模式定义必须指出适用界面和失效条件。
- 视觉判断不确定时应升级为异常或人工确认。
