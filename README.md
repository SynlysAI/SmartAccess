# SmartAccess

<p align="center">
  <img src="resource/icon.png" alt="SmartAccess icon" width="128">
</p>

SmartAccess 是一个面向科学仪器上位机软件的非侵入式实验接入与执行助手。它通过 `AI Agent + UI 自动化 + OCR 观测 + 平台适配` 的组合，把原本分散、手工、异构的实验操作流程沉淀为可执行、可回放、可审计的标准工作流。

当前仓库定位为`产品与架构基线`，并已进入桌面端实现阶段。下一阶段主模型收敛为“锚点 -> 工作流 -> 执行”：锚点是可操作区域，每个锚点最多绑定一个可选 OCR 观测区域；工作流步骤执行动作后，有预期 OCR 就轮询判断，没有观测就等待默认秒数。

## 产品定位

### 是什么

- 一个运行在实验室侧的 PyQt 桌面执行层。
- 一个连接 SpecLabOS 的非侵入式仪器接入方案，核心依赖 UI 模拟操作、截图裁剪、OCR 读取和结构化 trace 回传。
- 一个把“锚点配置、工作流设计、模板发布、运行执行”串成闭环的 AI 运行时。

### 不是什么

- 不是直接替代仪器原生控制软件的驱动层或固件层。
- 不是默认要求每台仪器开放 SDK、串口协议或私有 API 的深度集成方案。
- 不是首版支持复杂流程编排或多模式视觉识别的通用 RPA 平台。

## 核心价值

- 非侵入式接入：尽量不改动现有上位机软件和实验流程。
- AI 辅助配置：通过单 prompt 对话生成标准工作流，结合已保存锚点和运行时知识库。
- OCR 观测闭环：截图、裁剪、OCR 读取、文本匹配补齐接口缺口。
- 真实 UI 自动化：Win32 SendInput/SetCursorPos 驱动点击、输入、快捷键等动作原语。
- 数据统一回传：运行结果从 `run_trace.jsonl` 的步骤级事实提取并上传到 SpecLabOS。
- 可追溯和可扩展：以模板、契约和评测用例支撑后续仪器扩展。

## 核心文档

- [产品需求文档](docs/PRD.zh-CN.md)
- [技术规格说明](docs/SPEC.zh-CN.md)
- [系统架构总览](docs/architecture/system-overview.md)
- [软件总体设计](docs/architecture/software-design.md)
- [AI 组件设计](docs/architecture/ai-components.md)
- [关键契约与样例](docs/contracts/interfaces.md)
- [功能更新日志](docs/CHANGELOG.zh-CN.md)
- [近期实现更新 2026-06-11](docs/recent-updates-2026-06-11.md)
- [仓库级 Agent 协作约束](ai/AGENT.md)

## 仓库结构

```text
.
├── README.md
├── resource/
│   └── icon.png
├── docs/
│   ├── PRD.zh-CN.md
│   ├── SPEC.zh-CN.md
│   ├── CHANGELOG.zh-CN.md
│   ├── architecture/
│   │   ├── system-overview.md
│   │   ├── software-design.md
│   │   └── ai-components.md
│   └── contracts/
│       ├── interfaces.md
│       └── examples/        # anchors/workflow/platform/run_trace/eval 样例
├── src/smartaccess/
│   ├── bootstrap/           # 依赖注入与桌面启动
│   ├── desktop/             # PyQt6 工作台
│   │   ├── pages/           # 锚点/工作流/模板平台/执行
│   │   ├── shell/           # 主窗口/主题/应用入口
│   │   ├── viewmodels/      # UI 状态与数据绑定
│   │   └── widgets/         # 可复用组件（截图画布/步骤表/日志视图等）
│   ├── runtime/
│   │   ├── adapters/        # Win32自动化/OCR/DeepSeek/SpecLabOS
│   │   ├── application/     # 服务层（锚点/工作流/模板平台/运行/AI知识库）
│   │   └── orchestration/   # 编排器/执行器/观测器/恢复引擎
│   └── shared/
│       ├── config/          # 应用配置
│       ├── contracts/       # YAML契约模型（anchors/workflow/run_trace）
│       └── events/          # 事件总线与运行时事件
├── tests/
│   ├── contract/            # 契约样例验证
│   ├── integration/         # 服务/编排/外观集成测试
│   └── desktop/             # 桌面冒烟测试
├── workspace/               # 运行时工作区（锚点集/工作流草稿/模板/AI知识库）
└── ai/                      # memory/skills/agents/harness
```

### `src/smartaccess/`

- `bootstrap/`：依赖注入、提供者装配与桌面启动入口。
- `desktop/`：PyQt6 工作台，主导航为 `锚点`、`工作流`、`模板/平台`、`执行` 四个一级页面。
- `runtime/adapters/`：Win32 真实自动化、本地 OCR、DeepSeek AI 生成器、SpecLabOS HTTP 客户端及对应 stub。
- `runtime/application/`：AnchorService、WorkflowService、TemplateService、PlatformSyncService、RunService、AIRuntimeStore 等服务层。
- `runtime/orchestration/`：Orchestrator 编排器、Executor 执行器、Observer 观测器、RecoveryEngine 恢复引擎。
- `shared/`：应用配置、Pydantic 契约模型（anchors / workflow / run_trace）、事件总线。

### `workspace/`

- `anchors/`：已保存锚点集（`anchors.yaml`）。
- `workflows/`：工作流草稿（`draft.yaml`）。
- `templates/`：本地模板副本（`{template_id}/{version}/workflow.yaml`）。
- `runs/`：运行轨迹、截图和导出产物。
- `ai-runtime/`：AI 运行时知识库（episodes / memory / skills / index.json）。

## 体系总览

![SmartAccess 架构总览](docs/refer/SmartAccess.png)

上图中的关键关系已经在 [系统架构总览](docs/architecture/system-overview.md) 中文字化，重点包括：

- `Action Flow`：用户意图经 AI Agent 生成线性工作流，再驱动 UI 自动化执行。
- `Data Flow`：上位机状态、OCR 事实、运行日志、截图路径回流到 SmartAccess 和 SpecLabOS。
- `API Flow`：SmartAccess 通过 FastAPI 适配层与 SpecLabOS 双向同步任务、模板和执行状态。

## AI 组件分层

### 产品运行时 AI

- `memory/product/`：动作原语、锚点配置、OCR 观测、恢复规则。
- `skills/runtime/`：工作流设计、UI 编排、锚点标注、平台映射、异常恢复。
- `agents/runtime/`：orchestrator、executor、observer、recovery。
- `harness/runtime/`：运行时装配、事件总线、会话边界、审计约束。

### 仓库协作 AI

- `memory/repo/`：项目背景、术语、路线图。
- `skills/repo/`：PRD 维护、架构一致性检查、README 维护、文档同步。
- `agents/repo/`：product-analyst、technical-writer、architecture-steward。
- `harness/evals/`：关键场景回归评测和契约验收。

## 文档同步约束

每次完成会影响产品行为、运行时契约、UI 语义、工作流字段或 AI 组件的改动后，都需要执行项目级 `ai/skills/repo/documentation-sync`：同步更新功能日志、PRD、SPEC、契约说明、README、memory 和相关 skill，避免实现与文档脱节。

## 环境配置

推荐使用 Conda 环境名 `smartaccess`：

```bash
conda env create -f environment.yml
conda activate smartaccess
pip install -e ".[desktop,serve,dev]"
```

开发态配置从 `.env` 读取，可从示例复制：

```bash
copy .envexample .env
```

关键变量：

- `SMARTACCESS_WORKSPACE_DIR`：运行时工作区，默认 `workspace`。
- `SMARTACCESS_VISION_PROVIDER`：桌面真实 OCR 使用 `local`，测试可用 `stub`。
- `SMARTACCESS_UDP_HOST` / `SMARTACCESS_UDP_PORT`：Edge API 下发 UDP 执行信号的目标。
- `SMARTACCESS_WORKFLOW_GENERATOR`、`DEEPSEEK_API_KEY`：配置在线工作流/锚点生成能力。
- `SMARTACCESS_AI_PROVIDER` / `SMARTACCESS_AI_BASE_URL` / `SMARTACCESS_AI_MODEL` / `SMARTACCESS_AI_API_KEY`：OpenAI-compatible 多模型配置。
- `SMARTACCESS_AI_TIMEOUT_SECONDS`：AI 请求超时，单位秒。
- `SMARTACCESS_AI_USER_AGENT`：AI 请求头中的 `User-Agent`，用于兼容部分网关或 Cloudflare 策略。

### AI 配置与接入

- 工作流草稿生成和设备接入页的 AI 辅助接入都已统一到 OpenAI-compatible 生成链路。
- 桌面端设备接入页允许临时切换 `AI provider`、`AI base URL`、`AI model`，但不会把 API key 写入 workspace。
- 设备接入页发起 AI 辅助接入时，会把当前窗口截图作为多模态上下文一并发送，用于生成简化后的 `anchors.yaml` 建议。
- `DEEPSEEK_*` 旧配置仍兼容；当 `SMARTACCESS_AI_*` 存在时优先使用新配置。
- 启动时会自动读取项目根目录 `.env`；系统环境变量仍优先于 `.env`。

### Cloudflare / 网关限制

- 如果 AI 请求返回 `HTTP 403 Cloudflare 1010`，说明端点拦截了当前请求指纹，不是本地 YAML 或 OCR 配置错误。
- 运行时会自动带上浏览器风格的 `User-Agent`、`Origin`、`Referer` 请求头，并把错误压缩成可操作提示。
- 如果仍被拦截，优先调整 `SMARTACCESS_AI_USER_AGENT`，或者让模型服务提供方放行该 API 客户端。

## 新增一个仪器接入的最小步骤

1. 在 `docs/contracts/` 明确该仪器的 `anchors.yaml`、平台字段映射和运行 trace 读取方式。
2. 在 `ai/memory/product/` 补充锚点、动作能力、OCR 观测和安全限制。
3. 在 `ai/skills/runtime/` 选择或新增对应的工作流设计、锚点标注、平台映射技能。
4. 在 `ai/agents/runtime/` 明确 orchestrator、executor、observer、recovery 的职责分配。
5. 在 `ai/harness/evals/cases/` 新增回归用例，覆盖首次接入、执行、OCR 命中/超时、异常和回传。

## 观察区域锚点编辑

1. 在设备接入页先选择目标窗口并捕获截图。
2. 为可点击或输入位置添加动作锚点，例如 `搜索框`、`文本输入`、`发送按钮`。
3. 如果某个动作后需要 OCR 校验，勾选该锚点的 `OCR观测`，系统会创建或使用 `{锚点ID}_observe` 观察区域。
4. 动作区域用于点击、输入和聚焦；观察区域只用于 OCR 读取。两者可以重合，也可以分开拖拽。
5. 保存后 `anchors.yaml` 会同时写入 pixel 和 normalized 坐标，运行时按当前窗口尺寸映射。

## OCR 配置与执行逻辑

- 本地 OCR provider 是 `LocalVisionProvider`，依赖 `opencv-python`、`paddleocr` 和 `paddlepaddle`。
- 锚点配置在 `anchors.yaml`：`action_region` 用于点击/聚焦，`observe_region` 用于动作后的 OCR 读取。
- 工作流配置在 `workflow.yaml`：步骤用 `expected_text`、`match_mode`、`timeout_seconds` 声明 OCR 预期；`match_mode: none` 表示不做 OCR。
- Orchestrator 先执行动作；无 OCR 时按 `step.wait_seconds -> anchor.default_wait_seconds -> 0` 固定等待；有 OCR 时每 0.5 秒截图、裁剪 observe region、识别并匹配文本。
- 每步都会写入 `run_trace.jsonl`，包含期望 OCR、实际 OCR、匹配结果、尝试次数、耗时、截图路径和错误详情。

## 能力示例

受版本控制的示例位于 `docs/contracts/examples/`，用于证明系统能力和作为导入 workspace 前的模板。

### 串口调试助手 UDP

- 锚点集：`docs/contracts/examples/serial_debug_assistant_udp/anchors.yaml`
- 工作流：`docs/contracts/examples/serial_debug_assistant_udp/workflow.yaml`
- 覆盖能力：选择 UDP 模式、设置本地端口、打开 UDP 服务、输入并发送 `SmartAccess UDP validation`，再用 OCR 检查收发日志。
- 运行前打开目标“串口调试助手/网络调试助手”，把示例锚点导入或按示例重新框选坐标，确认窗口标题包含“串口调试助手”。
- workspace 中同时提供了可直接测试的草稿：
  `workspace/anchors/serial_debug_assistant_udp/anchors.yaml`
  `workspace/instruments/serial_debug_assistant_udp/instrument_profile.yaml`
  `workspace/workflows/wf_serial_debug_assistant_udp_send/draft.yaml`
- workspace 版本按 `1322x914` 截图基准保存，并给打开/发送相关锚点配置了 OCR 观察区。

### Windows 计算器

- 锚点集：`docs/contracts/examples/windows_calculator/anchors.yaml`
- 工作流：`docs/contracts/examples/windows_calculator/workflow.yaml`
- 覆盖能力：聚焦计算器、输入 `12+34`、回车计算，并用 OCR 检查结果区包含 `46`。
- 运行前打开 Windows 计算器标准模式，确保窗口可见、无遮挡，并按当前窗口尺寸校准结果显示区和按键焦点锚点。

### 运行方法

1. 启动桌面端：`python run_desktop.py`。
2. 在“设备接入与校准”页扫描目标窗口，按示例创建或导入锚点集，保存到 `workspace/anchors/{profile_id}/anchors.yaml`。
3. 在“工作流设计”页选择锚点集，载入或按示例保存 workflow 到 `workspace/workflows/{workflow_id}/draft.yaml`。
4. 运行标准化检查，通过后切到“运行监控”页选择工作流并开始。
5. 查看步骤时间线、步骤审计、OCR 文本、截图链接和 `run_trace.jsonl`。

## v2 简化模型特性

- ✅ 四页主导航：锚点、工作流、模板/平台、执行
- ✅ `anchors.yaml` 作为唯一锚点配置
- ✅ 简化 `workflow.yaml`：线性步骤 + anchor_id + action + expected_text/match_mode
- ✅ OCR-only 观测链路：截图、裁剪、OCR 读取、文本匹配
- ✅ 真实 Win32 UI 自动化（click/type/hotkey/press_enter；双击用两个连续 click 步骤表达）
- ✅ `run_trace.jsonl` 自动记录每步 OCR 事实、截图路径、等待策略和错误详情
- ✅ 平台从 trace 提取结果
- ✅ 模板/平台仍为一级入口，但只发布和回拉新简化 workflow

## 推荐开发顺序

1. 先固化契约：`anchors.yaml`、`workflow.yaml`、`platform_adapter.yaml`、`run_trace.jsonl`、`eval_case.yaml`。
2. 再实现锚点页：窗口扫描、截图、画布、action/observe 区域保存。
3. 接着实现工作流页：锚点集选择、单 prompt 生成、步骤表和标准化检查。
4. 然后实现执行页：开始/停止/取消、OCR 轮询、截图、日志和 trace。
5. 最后补模板/平台闭环：模板发布、回拉、状态/trace 上传、评测自动化。

## 验证

```bash
# 运行全部测试
python -m pytest tests/ -v

# 启动桌面工作台（需 PyQt6 + opencv-python + paddleocr）
python run_desktop.py

# 启动 Edge API，向串口/流程执行主机发送 UDP 执行信号
smartaccess-edge
```

## 当前默认假设

- MVP 以 `Windows` 上位机场景为主，`Linux` 支持进入 V1。
- v2 只支持线性顺序工作流，复杂流程控制进入后续版本评估。
- 平台需要结果时从 run trace 中读取每步 OCR 事实。
- 工作流 AI 界面只有一个 prompt 输入；锚点集选择属于工作流上下文，不作为 prompt token/reference 暴露给用户。
- 研发工作以“文档先行、契约先行、评测先行”为原则。
