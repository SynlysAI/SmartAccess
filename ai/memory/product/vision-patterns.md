# Vision Patterns Memory

- `scope`: SmartAccess OCR 观测策略与锚点区域约束。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-07-21
- `related_contracts`: `anchors.yaml`, `run_trace.jsonl`

## 视觉校验与 OCR

- 锚点执行前校验支持 `image`、`text` 和 `image_text`。
- OCR 工作流步骤读取锚点 `action_region` 内文字。
- 文本匹配：对 OCR 文本执行 `contains`、`equals`、`regex`、`not_empty` 或 `none` 判断。

## 坐标与鲁棒性

- 锚点配置阶段应同时保存 pixel region 与 normalized region。
- 运行时优先用 normalized region 按当前窗口尺寸重映射坐标。
- `action_region` 是动作目标，也是 OCR 步骤的读取区域。
- `precheck.region` 是动作执行前用于防止点错窗口或位置的校验区域。

## 约束

- 视觉判断不确定时应升级为异常或人工确认。
- 文字执行前校验固定使用忽略大小写、NFKC 和空白归一化后完全相等判断。
- OCR 结果、置信度、匹配结果、尝试次数和截图路径必须写入 `run_trace.jsonl`。
- 运行监控日志展示 OCR 观测事件时，必须同时展示 pass 规则（`match_mode + expected_text` 或 `not_empty`）、实际 OCR 文本、匹配结果和尝试次数，便于不打开 trace 也能审计历史识别事实。
- OCR mismatch 触发 `run.failed` 时，失败事件也必须携带同一组 OCR 调试字段，ERROR 日志要高亮 pass 规则和当前实际识别结果。
- 运行日志必须在 `run.started` 输出 START 边界，在 `run.completed`、`run.failed`、`run.cancelled` 输出 END 边界；边界至少包含设备 ID、作者、工作流名称和 session。

## 能力样例

- 串口调试助手 UDP 示例可用状态锚点的 `action_region` 读取服务状态和收发日志。
- Windows 计算器示例用结果锚点的 `action_region` 读取 `46`，证明 `12+34` 运算结果。
