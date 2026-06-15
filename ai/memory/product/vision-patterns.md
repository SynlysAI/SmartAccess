# Vision Patterns Memory

- `scope`: SmartAccess OCR 观测策略与锚点区域约束。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-11
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

## 能力样例

- 串口调试助手 UDP 示例用按钮状态区和收发日志区作为 `observe_region`，证明打开服务和发送文本。
- Windows 计算器示例用结果显示区作为 `observe_region`，OCR 文本需包含 `46` 来证明 `12+34` 运算结果。
