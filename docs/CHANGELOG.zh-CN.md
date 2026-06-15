# SmartAccess 功能更新日志

本文件记录已落地或已明确进入实现基线的产品能力。详细产品范围以 `docs/PRD.zh-CN.md` 为准，技术语义以 `docs/SPEC.zh-CN.md` 与 `docs/contracts/interfaces.md` 为准。

## 2026-06-15 运行监控设备摘要与 OCR 日志增强

### 运行监控
- 运行监控页在工作流下拉框下方展示当前工作流绑定的锚点集/设备摘要，包括工作流状态、模板版本、绑定锚点集、窗口签名、锚点数量、OCR 观测锚点数量和动作能力。
- 当工作流引用的锚点集不存在时，监控页显示“未找到绑定设备配置”，不阻断用户查看或切换工作流。
- 运行日志对 `run.step.observed` OCR 观测事件追加 `OCR规则`、`OCR实际`、`匹配` 和 `尝试` 信息，便于从历史日志直接审计预期 pass 规则和实际识别结果。
- 运行监控页的工作流设备摘要、会话审计、最新 OCR 观测和运行日志改为富文本展示，区分标题、字段名、关键值和错误/警告状态。
- OCR mismatch 导致 `run.failed` 时，事件 payload 附加 `match_mode`、`expected_text`、`actual_text`、`matched`、`attempts`、耗时、截图和等待策略；ERROR 日志同步高亮 OCR pass 规则和实际识别结果。
- 工作流绑定设备摘要改为自适应三列信息评估布局，按“基础信息 / 设备评估 / 能力评估”分组展示，充分利用顶部横向空间，并允许长窗口标题、动作列表按宽度换行，避免信息被压缩裁剪。
- 运行日志取消横向单行滚动，按当前控件宽度自动换行；OCR 调试字段拆分为可换行字段组，方便查看长失败信息。

### 工作流设计
- 工作流页底部“信息”区改为富文本展示，AI reasoning 与检查结果按标题和正文分层显示。

### 验证
- 新增 `tests/desktop/test_monitoring_page.py` 覆盖绑定设备摘要、缺失设备提示、OCR 日志展开和非 OCR 日志保持简洁。
- 已执行 `pytest tests/desktop/test_monitoring_page.py -q`。
- 新增 `tests/desktop/test_workflow_result_rich_text.py` 和 `tests/integration/test_ocr_failed_event_payload.py`，覆盖工作流信息富文本和 OCR 失败事件调试 payload。
- 已执行 `pytest tests/desktop/test_workflow_result_rich_text.py -q`、`pytest tests/integration/test_ocr_failed_event_payload.py -q` 和 `python -m compileall -q src\\smartaccess ...`。
- 已补充执行 `pytest tests/desktop/test_monitoring_page.py tests/desktop/test_workflow_result_rich_text.py tests/integration/test_ocr_failed_event_payload.py -q`，覆盖摘要换行、日志换行和 OCR 字段排布。
- 当前更宽的集成/契约测试仍受既有导出问题阻塞：`smartaccess.shared.events` 未导出 `RuntimeEventName`，`smartaccess.shared.contracts` 未导出 `AnchorsContract`。

## 2026-06-11 VER5 能力示例与监控增强

### 运行监控
- 步骤时间线在窗口尺寸变化时重新计算行高，长 `anchor_id`、`value` 和状态文本可完整换行显示。
- 步骤审计改为可滚动、可选择的富文本区域；截图、trace、workflow、anchors 引用以可点击文件链接展示。

### 工作流与示例
- 工作流 AI 助手输入框不再预填“打开方法编辑器，设定目标参数，启动运行并等待状态变化。”，仅保留 placeholder。
- 新增串口调试助手 UDP 示例：`docs/contracts/examples/serial_debug_assistant_udp/`。
- 新增 Windows 计算器 OCR 示例：`docs/contracts/examples/windows_calculator/`，通过 `12+34=46` 证明 OCR 结果。
- Eval harness 从 5 个场景扩展到 7 个场景。

### 配置与环境
- 新增 `.envexample` 和 `environment.yml`，Conda 环境名为 `smartaccess`。

## 2026-06-11 VER4 规划基线

### 简化重构计划评审
- 确认主模型收敛为“锚点 -> 工作流 -> 执行”，锚点是动作区域，每个锚点最多绑定一个可选 OCR 观测区域。
- 保留 `模板/平台` 作为一级入口，主导航固定为 `锚点`、`工作流`、`模板/平台`、`执行`。
- 明确本次是断代重建，主路径只保留锚点集、线性步骤、OCR 预期和步骤级 trace 事实。

### 契约断代
- 新增 `anchors.yaml` 作为唯一锚点配置。
- 简化 `workflow.yaml`：metadata 使用 `anchor_profile`，steps 只保留 `anchor_id`、`action`、`value?`、`expected_text?`、`match_mode`、等待和确认字段。
- `run_trace.jsonl` 改为步骤级事实记录，自动记录动作、等待策略、期望 OCR、实际 OCR、匹配结果、尝试次数、耗时、截图路径和错误详情。
- 平台结果由 trace 提取，平台字段差异只在适配器中处理。

### 运行与 UI 语义
- Orchestrator 统一后置流程：动作后有 OCR 预期则轮询 observe region，否则按步骤、锚点或应用默认等待。
- Executor 明确定义动作语义：点击类动作点击 `action_region` 中心，输入类动作先聚焦锚点再输入或按键。
- Observer/VisionProvider 收敛为 OCR-only，只保留截图、裁剪、OCR 读取和文本匹配。
- 锚点页保留窗口扫描、截图、画布和锚点表；工作流页保留锚点集选择、单 prompt、生成按钮和 step 表；执行页展示期望 OCR、实际 OCR、截图路径和日志。

### 文档同步
- 已同步 README、PRD、SPEC、系统架构、软件设计、AI 组件设计、契约说明、契约样例、AI memory、runtime skill、runtime agent、harness、eval case、微信 demo 文档和 workspace demo YAML。
- 后续实现需同步替换代码层契约模型、服务、UI 页面和测试夹具。
