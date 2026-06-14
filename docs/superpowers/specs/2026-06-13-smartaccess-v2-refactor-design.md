# SmartAccess v2 重构设计

## 目标

在不改动旧 `src/smartaccess` 实现的前提下，新建 `src/smartaccess_v2`，用更轻、更清晰的结构完整复刻 SmartAccess 当前功能，并修复已知界面、校准、工作流、运行和日志问题。

允许新增根目录启动脚本 `run_desktop_v2.py`。除该入口外，产品实现代码限定在 `src/smartaccess_v2`。

## 数据目录

v2 默认使用独立数据目录 `workspace_v2`：

```text
workspace_v2/
  anchors/{profile_id}/anchors.yaml
  workflows/{workflow_id}/draft.yaml
  templates/{template_id}/{version}/workflow.yaml
  runs/{session_id}/run_trace.jsonl
  runs/{session_id}/screenshots/
  logs/smartaccess.log
  app_state/window_state.json
  outbox/platform_outbox.jsonl
```

v2 不默认读取旧 `workspace`，避免污染现有数据。后续提供导入旧数据能力时，采用复制、校验、写入 `workspace_v2` 的方式。

## 包结构

```text
src/smartaccess_v2/
  bootstrap/
  shared/
    config/
    contracts/
    events/
  runtime/
    adapters/
    application/
    domain/
    orchestration/
    api/
  desktop/
    pages/
    shell/
    viewmodels/
    widgets/
```

稳定且无需大改的旧实现可以复制到 v2 包内，复制后调整 import、注释和必要结构。v2 不依赖旧 `smartaccess` 包的内部模块。

## 功能范围

v2 需要保留以下功能：

- 设备接入与校准：窗口扫描、截图、ROI 画布、动作锚点、OCR 观察区、AI 辅助生成锚点、保存/加载/删除设备。
- 工作流设计：选择锚点集、AI 生成、手动编辑步骤、插入/删除/上移/下移、OCR 条件编辑、标准化检查、保存草稿。
- 等待动作：`action: wait` 作为独立步骤，配置等待秒数，不要求 `anchor_id`。
- 运行监控：选择工作流、开始/停止/取消、步骤时间线、日志、OCR 结果、截图路径、审计摘要。
- 模板/平台：本地模板、发布、刷新云端、搜索过滤、更新锚点、回滚、删除。
- 运行概览：设备数、模板数、最近运行、异常、补传状态。
- Edge API：保留 health、trigger、execute、status 四个端点。
- AI 接入：保留 OpenAI-compatible、Codex、DeepSeek 兼容生成器，锚点生成支持截图上下文。
- 真实适配：保留 Win32 自动化、窗口扫描、截图、LocalVision OCR、Stub provider。

## 优化项

设备接入与校准：

- 取消 OCR 勾选时同步删除观察区 ROI。
- 删除锚点时同步删除动作区和观察区 ROI。
- ROI 拖拽/缩放时实时更新表格坐标。
- 锚点配置表格支持手动调整列宽。
- 动作区域和观察区域只显示坐标 `(x,y,w,h)`，不混入 ROI 名称长字符串。

工作流：

- 新增可插入等待动作，保存为 `action: wait`。
- 步骤表按钮使用清晰图标或短文本表示上移、下移、删除。
- 标准化检查允许 `wait` 步骤无锚点，同时校验等待时间有效。

界面：

- 使用浅色客户端主题，不在界面上显示 v2 字样。
- 保存主窗口尺寸、最大化状态、dock/面板显示状态、splitter 比例。
- 最小化恢复和切换功能页不自动还原布局。
- 页面避免嵌套卡片和大面积深色背景，优先表格、分栏、工具栏。

日志与运行：

- `run_desktop_v2.py` 配置终端日志。
- 关键启动、扫描、保存、运行、异常和平台同步事件输出到控制台。
- 日志同时写入 `workspace_v2/logs/smartaccess.log`。
- 固定等待和 OCR 轮询都支持停止/取消检查，不再长时间阻塞。

平台同步：

- outbox 使用 `workspace_v2/outbox/platform_outbox.jsonl` 持久化，重启后仍可补传。

## 契约

`anchors.yaml` 保持现有核心结构：

- `profile_id`
- `window_signature`
- `anchors`
- `action_region`
- `observe_region`
- `supported_actions`
- `default_wait_seconds`
- `action_bindings`

`workflow.yaml` 保持现有结构并扩展 `WorkflowStep.action`：

- 动作步骤：`click`、`type`、`hotkey`、`press_enter`，必须有 `anchor_id`。
- 等待步骤：`wait`，不需要 `anchor_id`，使用 `wait_seconds` 或 `value`。
- OCR 检查：继续由动作步骤的 `expected_text`、`match_mode`、`timeout_seconds` 表示。
- 旧式内联等待 `wait_seconds` 继续兼容。

`run_trace.jsonl` 继续记录：

- `timestamp`
- `session_id`
- `workflow_id`
- `step_id`
- `anchor_id`
- `action`
- `wait_strategy`
- `expected_text`
- `actual_text`
- `match_mode`
- `matched`
- `attempts`
- `elapsed_seconds`
- `screenshot_path`
- `status`
- `error`

## 运行流程

1. 用户选择工作流并开始运行。
2. `RunSessionService` 创建 session，初始化步骤状态。
3. `Orchestrator` 逐步执行：
   - `wait` 步骤只做可取消等待并写 trace。
   - 动作步骤先定位窗口和锚点，再执行动作。
   - `match_mode == none` 时使用固定等待。
   - 有 OCR 条件时截图、裁剪 observe region、OCR、匹配，直到命中、超时或停止。
4. 每个阶段发运行事件。
5. UI 更新时间线、日志、OCR 结果、截图路径、审计摘要。
6. trace 和截图写入 `workspace_v2/runs/{session_id}`。
7. 用户停止/取消时设置 stop token，等待和轮询尽快退出。

## UI 方向

界面采用浅色客户端风格：

- 左侧固定主导航。
- 顶部工具栏显示面板切换、设置、当前 workspace 和关键操作。
- 主区域按页面职责分栏。
- 校准页左侧为截图/ROI 画布，右侧为锚点配置表格。
- 右侧上下文栏显示设备、AI、风险、日志等辅助信息。
- 表格列宽可拖动，按钮可识别，坐标短显示。

品牌显示为 `SmartAccess`，不显示 `v2`。

## 分批实施

1. v2 基础骨架：入口、配置、日志、契约、事件、空主窗口。
2. 设备接入与校准：窗口扫描、截图、ROI、锚点表格、保存加载删除。
3. 工作流设计：步骤表、AI 生成、保存、标准化、等待动作。
4. 运行监控与编排：执行、OCR、trace、截图、停止取消、日志。
5. 模板/平台/概览/Edge API：模板管理、outbox、dashboard、API。
6. 收尾与迁移：旧数据导入、UI 状态持久化、手动验证和必要测试。

## 验收标准

- `python run_desktop_v2.py` 能启动 SmartAccess 浅色客户端。
- 默认数据写入 `workspace_v2`。
- 旧 `src/smartaccess` 不被修改。
- 校准页修复待办中的 ROI 同步问题。
- 工作流支持插入 `wait` 步骤。
- 最小化恢复和页面切换不重置主窗口/面板布局。
- 终端能看到关键日志和异常。
- 基础运行能生成 `run_trace.jsonl` 和截图路径。
- 模板/平台/概览/Edge API 的旧功能在 v2 中具备对应入口。
