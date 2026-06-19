# Vision Patterns Memory

- `scope`: SmartAccess OCR 观测策略与锚点区域约束。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-19
- `related_contracts`: `anchors.yaml`, `run_trace.jsonl`

## v2 观测模式

- OCR：唯一主路径，用于读取锚点 `observe_region` 内文字。
- 文本匹配：对 OCR 文本执行 `contains`、`equals`、`regex`、`not_empty` 或 `none` 判断。
- none：表示该步骤不做 OCR 判断，只执行默认等待。

## 坐标与鲁棒性

- 锚点配置阶段应同时保存 pixel region 与 normalized region。
- 运行时优先用 normalized region 按当前窗口尺寸重映射坐标。
- `action_region` 是动作目标；`observe_region` 是动作后的 OCR 读取目标。
- 一个锚点最多绑定一个 `observe_region`，避免重新引入额外区域映射层。

## 约束

- 视觉判断不确定时应升级为异常或人工确认。
- v2 不使用非 OCR 识别模式；这些能力如需恢复，必须先更新主契约和评测。
- OCR 结果、置信度、匹配结果、尝试次数和截图路径必须写入 `run_trace.jsonl`。
- 运行监控日志展示 OCR 观测事件时，必须同时展示 pass 规则（`match_mode + expected_text` 或 `not_empty`）、实际 OCR 文本、匹配结果和尝试次数，便于不打开 trace 也能审计历史识别事实。
- OCR mismatch 触发 `run.failed` 时，失败事件也必须携带同一组 OCR 调试字段，ERROR 日志要高亮 pass 规则和当前实际识别结果。
- 运行日志必须在 `run.started` 输出 START 边界，在 `run.completed`、`run.failed`、`run.cancelled` 输出 END 边界；边界至少包含设备 ID、作者、工作流名称和 session。

## 能力样例

- 串口调试助手 UDP 示例用按钮状态区和收发日志区作为 `observe_region`，证明打开服务和发送文本。
- Windows 计算器示例用结果显示区作为 `observe_region`，OCR 文本需包含 `46` 来证明 `12+34` 运算结果。
