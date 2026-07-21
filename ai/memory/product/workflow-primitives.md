# Workflow Primitives Memory

- `scope`: SmartAccess 运行时允许使用的基础工作流动作和等待语义。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-07-21
- `related_contracts`: `workflow.yaml`, `anchors.yaml`, `run_trace.jsonl`

## 原语集合

- `click`
- `type`
- `hotkey`
- `press_enter`
- `ocr`
- `wait`

## 动作语义

- `click` 点击目标锚点 `action_region` 中心；双击用两个连续 `click` 步骤表达。
- `type` / `hotkey` / `press_enter` 必须先聚焦目标锚点，再输入或按键。
- `type` 步骤的 `input_mode` 默认为 `free`，直接使用 `value`。
- `type` 步骤可声明 `input_mode: incrementing` 和 `increment_rule`，运行时解析为真实输入值，不修改原始 workflow。
- 每个 `type + incrementing` 步骤独立保存自己的 `increment_rule`；桌面端通过动作参数弹窗编辑模板、变量名、日期格式和循环范围。
- 默认递增模板为 `{device_id}-{author}-{date}-{counter:03d}`，`date_format` 默认 `%Y%m%d`，计数按 `workflow_id + sequence_key` 持久化；同一次 run session 内相同变量复用同一个值，成功完成后才推进下次值。
- 每个原语都必须可落到 `run_trace.jsonl` 的步骤级事实。
- 高风险步骤使用 `requires_confirmation`，执行前必须等待人工确认。

## 等待与观测语义

- `ocr` 必须单独作为一步，并对目标锚点的 `action_region` 做 OCR 轮询。
- OCR 匹配支持 `contains`、`equals`、`regex`、`not_empty`、`none`。
- OCR 的 `timeout_seconds` 缺省为 `10.0s`，`poll_interval_seconds` 缺省为 `0.5s`，两者均可按步骤配置。
- 非 `wait` 步骤成功后按 `step.wait_seconds` 等待；缺省为 `1.0s`，显式 `0` 表示不等待。
- `wait` 步骤的 `wait_seconds` 表示该步骤自身的等待时长。
- 停止或取消请求必须能中断 OCR 轮询。
- 递增式输入写入 trace 时，`action.value` 必须是解析后的真实输入值。

## 禁止重新引入的旧语义

- 不再使用截图校验动作、流程控制动作或截图采集动作作为工作流动作。
- 不再使用复杂绑定、手工结果声明或步骤级自由判断。
- 平台需要结果时从 `run_trace.jsonl` 读取每步 OCR 事实。
