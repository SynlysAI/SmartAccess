# SmartAccess 功能更新日志

本文件记录已落地或已明确进入实现基线的产品能力。详细产品范围以 `docs/PRD.zh-CN.md` 为准，技术语义以 `docs/SPEC.zh-CN.md` 与 `docs/contracts/interfaces.md` 为准。

## 2026-06-09 VER3

### 校准页删除能力
- 安全/确认表增加删除列（×按钮），每行可独立删除。
- 已校准仪器列表增加右键菜单："加载配置" + "删除仪器"。
- 删除仪器前进行引用预检：扫描本地草稿和模板的引用数。被运行中 session 占用则拒删；仅被引用则允许高风险确认删除，不级联删除工作流/模板。

### 工作流页删除与默认展开
- 审阅区移除独立"已读设备上下文"模块；上下文信息整合到 AI 分析与推理面板。
- "已有工作流"默认展开。
- 工作流列表显示来源标识：草稿 (📝) 和本地模板 (📋)。
- 右键菜单增加"删除工作流"：草稿仅删本地 draft.yaml；本地模板副本先删云端版本，成功后再删本地（云端失败则本地保留）。

### 真实动作与视觉链路
- `click`, `double_click`, `type`, `hotkey`, `press_enter` 全部走 Win32 真实输入。
- 新增 `LocalVisionProvider`：OCR 用 PaddleOCR，模板匹配用 OpenCV `matchTemplate`，颜色检测用 HSV 距离，存在性检测用前景占比。
- 桌面默认装配真实 provider；状态栏显示 Automation/Vision/LLM 模式。
- 依赖缺失时 fail fast，不静默回退 stub。

### 反馈引导
- 校准页锚点标签页增加"如何使用 OCR / Template / Color / Presence"说明面板。
- 工作流页条件编辑器标注时间单位为秒，内嵌观测模式说明。
- 监控页观测结果区域增加识别结果解读文案（OCR/Template/Color/Presence 各自说明）。

### Wait 秒制修正
- DeepSeek prompt 明确要求所有等待单位为秒。
- 生成后标准化：`5000ms`、`5000 ms`、旧 `timeout` 自动转秒。
- AI 生成的裸数字 >= 1000 视为毫秒换算；301-999 保留但发出警告。

### AI 运行时知识库
- 新增工作区级 `workspace/ai-runtime/` 目录结构：
  - `episodes/` — 每次生成的完整记录（prompt、命中知识、生成结果、编辑 diff、运行结果）
  - `memory/pending|approved/` — 稳定规则、软件特性、风险提示
  - `skills/pending|approved/` — 可复用步骤模板、前置条件、推荐锚点和条件模式
  - `index.json` — 可搜索索引
- 生成时仅使用 approved 项；生成后自动抽取候选进入 pending。
- 推理面板展示本次命中 memory/skill ID，保证可追溯。

---

## 2026-06-09 VER1

### 运行监控

- 运行监控页调整为左侧步骤时间线、右侧标签页结构。
- 右侧标签页包含“观测与审计”和“日志”，便于在执行时同时区分识别结果、审计摘要和日志流。
- 步骤时间线显示步骤开始、观测、完成、阻断、失败等状态时间。
- 发起运行时会提示运行开始，并清空上一轮观测、审计和日志展示，避免历史 note 干扰本次运行判断。

### 右侧工具栏与 AI 助手状态

- 全局右侧面板从“上下文”改为“工具栏”。
- AI 助手区域展示当前接入模型、提供方和状态。
- 未接入在线模型时显示本地模板生成器/模拟模式；接入 DeepSeek 时显示具体模型名称和配置状态。

### 模板库与版本管理

- 模板库增加搜索和状态过滤。
- 选中模板版本后展示版本时间线，包含版本号、状态、发布时间/加载来源、来源和适用仪器。
- 增加版本更新、删除和回滚入口。
- 当前回滚语义明确为“切换当前发布版本”，不是完整文件历史恢复或平台级 Git 式回滚。

### 工作流设计

- ROI 绑定在 UI 中解释为“工作流逻辑名 -> 已校准锚点”。
- 输出项解释为“结果 key -> 观测来源/模式”。
- 优化 ROI 绑定表、输出表和步骤表的删除列布局，避免删除按钮文字裁切。
- 两个 WeChat 测试工作流保留复用同一批设备锚点，但绑定名调整为更接近业务用途的别名。

### 设备接入与校准

- 锚点表格优化类型、动作、识别、确认和删除列宽。
- 类型与识别方式说明展示完整的 anchor type 和 vision mode，不再只显示部分类型。
- 分辨率变化下的锚点坐标优先使用 normalized ROI 按当前窗口尺寸映射，absolute ROI 作为回退。
- 固定窗口比例仅作为降低失败概率的手段；更推荐 normalized ROI + 视觉反馈 + 运行前校验。

### 动作识别闭环

- Observer 支持按锚点 `vision_mode` 分派 OCR、presence、template、color、none。
- Workflow step 可携带 `condition`，用于声明观测 source、识别模式、判断方式、期望值和超时参数。
- Orchestrator 在步骤执行后优先观察 step condition 指定来源，并判断条件是否满足。
- `wait_until` 与 `screenshot_check` 从“占位等待/截图”进入可被观测条件驱动的闭环基线。
- run trace 记录 observation detail，为后续审计和平台回传保留依据。

### AI 自驱动工作流编排方向

- AI 编排基线从“生成 workflow 文本”升级为“在能力约束下生成 draft”。
- 后续编排需基于可用 anchors、动作能力、vision modes、模板和运行历史生成工作流草稿。
- 第一版坚持只生成 draft，不自动执行；高风险动作必须保留人工确认。

### 验证记录

- `python -m pytest tests/integration/test_services.py tests/integration/test_orchestration.py tests/contract/test_contract_examples.py` 通过，13 passed。
- `python -m pytest tests/desktop/test_shell_smoke.py` 在当前 Python 3.14 环境中因 PyQt6 缺失被 skip。
