# SmartAccess Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `src/smartaccess` 和 `run_desktop.py`，完整复刻 SmartAccess 现有功能，并以更轻的结构修复校准、工作流、界面布局和日志问题。

**Architecture:** v2 是独立包，默认读写 `workspace_v2`，不依赖旧 `smartaccess` 内部模块。UI 通过粗粒度 `RuntimeFacade` 访问服务，运行时通过契约模型、服务层、编排器和适配器解耦。

**Tech Stack:** Python 3.11+、PyQt6、Pydantic v2、PyYAML、FastAPI、Win32 API、OpenCV/PaddleOCR 可选。

---

## 文件结构

本计划允许创建：

- `run_desktop.py`：v2 桌面启动脚本。
- `src/smartaccess/**`：v2 全部产品实现。

本计划不修改：

- `src/smartaccess/**`
- 旧 `run_desktop.py`
- `pyproject.toml`

设计和计划文档已写入：

- `docs/superpowers/specs/2026-06-13-smartaccess-refactor-design.md`
- `docs/superpowers/plans/2026-06-13-smartaccess-refactor.md`

## Task 1: 基础骨架、配置和空主窗口

**Files:**
- Create: `run_desktop.py`
- Create: `src/smartaccess/__init__.py`
- Create: `src/smartaccess/__main__.py`
- Create: `src/smartaccess/bootstrap/__init__.py`
- Create: `src/smartaccess/shared/config/settings.py`
- Create: `src/smartaccess/shared/logging.py`
- Create: `src/smartaccess/desktop/shell/app.py`
- Create: `src/smartaccess/desktop/shell/main_window.py`
- Create: `src/smartaccess/desktop/shell/theme.py`

- [ ] **Step 1: 创建 v2 包目录和 `__init__.py`**

创建空包文件，保证 `python -m smartaccess` 可解析。

- [ ] **Step 2: 实现 `AppSettings`**

实现从 `.env` 和环境变量读取配置，默认 `workspace_dir=Path("workspace_v2")`，兼容现有 AI、SpecLabOS、UDP 配置变量。

- [ ] **Step 3: 实现日志配置**

实现 `configure_logging(settings)`：输出到控制台和 `workspace_v2/logs/smartaccess.log`，编码 UTF-8，日志级别由 `SMARTACCESS_LOG_LEVEL` 控制。

- [ ] **Step 4: 实现浅色主题**

创建浅色 QSS：白色主背景、浅灰边框、蓝色主按钮、危险色删除按钮、可读表格和输入框。

- [ ] **Step 5: 实现空主窗口**

主窗口显示 `SmartAccess`，左侧导航包含：设备接入与校准、工作流设计、运行监控、模板/平台、运行概览。保存窗口大小、最大化状态、导航栏/右栏显示状态到 `workspace_v2/app_state/window_state.json`。

- [ ] **Step 6: 实现启动入口**

`run_desktop.py` 加载 `.env`，创建 settings，配置日志，启动桌面。

- [ ] **Step 7: 手动验证启动**

运行：

```powershell
$env:PYTHONPATH="src"
python run_desktop.py
```

预期：显示浅色空主窗口；控制台输出启动日志；`workspace_v2/logs/smartaccess.log` 存在。

## Task 2: 契约、IO、事件和基础服务

**Files:**
- Create: `src/smartaccess/shared/contracts/base.py`
- Create: `src/smartaccess/shared/contracts/anchors.py`
- Create: `src/smartaccess/shared/contracts/workflow.py`
- Create: `src/smartaccess/shared/contracts/run_trace.py`
- Create: `src/smartaccess/shared/contracts/edge_api.py`
- Create: `src/smartaccess/shared/contracts/io.py`
- Create: `src/smartaccess/shared/contracts/validation.py`
- Create: `src/smartaccess/shared/events/bus.py`
- Create: `src/smartaccess/shared/events/runtime.py`

- [ ] **Step 1: 复制并整理契约基础类**

复制旧契约的稳定字段，调整 import 到 `smartaccess`，补充中文函数注释。

- [ ] **Step 2: 扩展 `WorkflowStep`**

允许 `action` 为 `click/type/hotkey/press_enter/wait`。当 action 为 `wait` 时不要求 `anchor_id`；当 action 为动作步骤时要求 `anchor_id`。

- [ ] **Step 3: 更新标准化校验**

`wait` 步骤跳过锚点检查，但必须有大于等于 0 的等待时间。动作步骤继续检查锚点、动作、OCR observe region 和 regex。

- [ ] **Step 4: 实现事件总线日志**

EventBus 保持线程安全，订阅者异常不破坏发布，同时记录异常日志。

- [ ] **Step 5: 验证契约加载**

用临时脚本读取现有 `docs/contracts/examples/anchors.yaml` 和 `workflow.yaml`，确认 v2 模型能加载。脚本运行后删除。

## Task 3: 适配器和依赖装配

**Files:**
- Create: `src/smartaccess/runtime/application/ports.py`
- Create: `src/smartaccess/runtime/adapters/automation_stub.py`
- Create: `src/smartaccess/runtime/adapters/window_scanner.py`
- Create: `src/smartaccess/runtime/adapters/win32_automation.py`
- Create: `src/smartaccess/runtime/adapters/vision_stub.py`
- Create: `src/smartaccess/runtime/adapters/local_vision.py`
- Create: `src/smartaccess/runtime/adapters/artifact_store.py`
- Create: `src/smartaccess/runtime/adapters/openai_compatible_generator.py`
- Create: `src/smartaccess/runtime/adapters/deepseek_generator.py`
- Create: `src/smartaccess/runtime/adapters/deepseek_instrument_generator.py`
- Create: `src/smartaccess/runtime/adapters/codex_generator.py`
- Create: `src/smartaccess/runtime/adapters/platform_stub.py`
- Create: `src/smartaccess/runtime/adapters/speclabos_client.py`

- [ ] **Step 1: 定义 ports**

定义 AutomationProvider、VisionProvider、PlatformClient、WorkflowDraftGenerator、InstrumentProfileDraftGenerator、ArtifactStore 等协议和 DTO。

- [ ] **Step 2: 复制 Stub、Win32、LocalVision 适配器**

调整 import，保留现有行为。

- [ ] **Step 3: 复制 AI 生成器**

保留 Cloudflare 1010 友好错误、截图上下文、JSON/YAML 解析。更新工作流提示词，允许生成 `wait` 步骤。

- [ ] **Step 4: 复制平台客户端和 artifact store**

默认使用 `workspace_v2`。

- [ ] **Step 5: 实现 bootstrap 装配**

实现 `build_runtime_facade(settings)`，按 settings 选择 real/stub provider。

## Task 4: 应用服务、facade 和 dashboard

**Files:**
- Create: `src/smartaccess/runtime/application/anchor_service.py`
- Create: `src/smartaccess/runtime/application/calibration_service.py`
- Create: `src/smartaccess/runtime/application/workflow_service.py`
- Create: `src/smartaccess/runtime/application/template_service.py`
- Create: `src/smartaccess/runtime/application/platform_sync_service.py`
- Create: `src/smartaccess/runtime/application/run_session_service.py`
- Create: `src/smartaccess/runtime/application/incident_service.py`
- Create: `src/smartaccess/runtime/application/workspace_service.py`
- Create: `src/smartaccess/runtime/application/facade.py`
- Create: `src/smartaccess/runtime/domain/*.py`

- [ ] **Step 1: 实现锚点服务**

读写 `workspace_v2/anchors/{profile_id}/anchors.yaml`，支持保存、加载、删除、引用检查。

- [ ] **Step 2: 实现工作流服务**

读写 `workspace_v2/workflows/{workflow_id}/draft.yaml`，支持生成、保存、删除、标准化检查。

- [ ] **Step 3: 实现模板和平台同步服务**

模板读写 `workspace_v2/templates`。outbox 持久化到 `workspace_v2/outbox/platform_outbox.jsonl`。

- [ ] **Step 4: 实现运行 session 和 incident 服务**

支持 created、ready、started、observed、succeeded、failed、completed、stopping、cancelled 状态语义。

- [ ] **Step 5: 实现 `RuntimeFacade`**

提供 UI 需要的粗粒度方法：设备、工作流、模板、运行、概览、AI 状态、订阅事件。

## Task 5: 设备接入与校准 UI

**Files:**
- Create: `src/smartaccess/desktop/viewmodels/base.py`
- Create: `src/smartaccess/desktop/viewmodels/calibration_vm.py`
- Create: `src/smartaccess/desktop/widgets/roi_canvas.py`
- Create: `src/smartaccess/desktop/widgets/anchor_table.py`
- Create: `src/smartaccess/desktop/pages/calibration_page.py`

- [ ] **Step 1: 实现 `RoiCanvas`**

支持截图背景、ROI 新增、删除、拖拽、缩放，发出 `roi_added`、`roi_removed`、`roi_changed` 信号。

- [ ] **Step 2: 实现 `AnchorTable`**

用结构化行模型保存 anchor id、动作区 ROI 名、观察区 ROI 名、动作、OCR 开关、确认开关。表格显示坐标短文本，列宽 interactive。

- [ ] **Step 3: 实现画布和表格同步**

新增/删除/拖动 ROI 时更新表格。取消 OCR 时删除观察区 ROI。删除锚点时删除动作区和观察区 ROI。

- [ ] **Step 4: 实现校准页**

窗口扫描、截图、AI 辅助接入、保存、加载、删除设备。

- [ ] **Step 5: 手动验证待办第 1 组**

验证 OCR 取消、删除锚点、拖拽坐标、列宽和短坐标显示。

## Task 6: 工作流设计 UI

**Files:**
- Create: `src/smartaccess/desktop/viewmodels/workflow_vm.py`
- Create: `src/smartaccess/desktop/widgets/workflow_step_table.py`
- Create: `src/smartaccess/desktop/widgets/condition_editor.py`
- Create: `src/smartaccess/desktop/pages/workflow_page.py`

- [ ] **Step 1: 实现步骤表**

支持动作、等待、anchor_id、value、OCR 条件、上移、下移、删除。

- [ ] **Step 2: 实现等待动作**

添加“插入等待”按钮，默认 `wait_seconds=1.0`，保存为 `action: wait`。

- [ ] **Step 3: 实现 AI 生成和保存**

调用 WorkflowService，保存到 `workspace_v2/workflows`。

- [ ] **Step 4: 实现标准化检查**

显示通过/失败详情。

- [ ] **Step 5: 手动验证待办第 2 组和按钮显示**

验证可插入等待动作，按钮可辨识。

## Task 7: 运行编排和监控 UI

**Files:**
- Create: `src/smartaccess/runtime/orchestration/executor.py`
- Create: `src/smartaccess/runtime/orchestration/observer.py`
- Create: `src/smartaccess/runtime/orchestration/orchestrator.py`
- Create: `src/smartaccess/runtime/orchestration/recovery.py`
- Create: `src/smartaccess/desktop/viewmodels/monitoring_vm.py`
- Create: `src/smartaccess/desktop/widgets/timeline.py`
- Create: `src/smartaccess/desktop/widgets/log_view.py`
- Create: `src/smartaccess/desktop/pages/monitoring_page.py`

- [ ] **Step 1: 实现 Executor 和 Observer**

动作执行、锚点定位、OCR 读取、文本匹配。

- [ ] **Step 2: 实现 Orchestrator**

支持动作步骤、等待步骤、固定等待、OCR 轮询、可取消等待、trace、截图、事件。

- [ ] **Step 3: 实现 MonitoringViewModel**

订阅事件，驱动时间线、日志、审计、OCR 结果。

- [ ] **Step 4: 实现运行监控页**

选择工作流、开始、停止、取消、状态展示。

- [ ] **Step 5: 手动验证运行和日志**

运行 stub workflow，确认终端日志、UI 日志、trace、截图路径。

## Task 8: 模板、平台、概览和 Edge API

**Files:**
- Create: `src/smartaccess/desktop/viewmodels/template_vm.py`
- Create: `src/smartaccess/desktop/viewmodels/dashboard_vm.py`
- Create: `src/smartaccess/desktop/pages/template_page.py`
- Create: `src/smartaccess/desktop/pages/dashboard_page.py`
- Create: `src/smartaccess/runtime/application/experiment_service.py`
- Create: `src/smartaccess/runtime/api/edge.py`

- [ ] **Step 1: 实现模板页**

发布、刷新云端、搜索过滤、更新锚点、回滚、删除。

- [ ] **Step 2: 实现运行概览页**

显示设备、模板、运行、异常、补传统计。

- [ ] **Step 3: 实现 Edge API**

复刻 `/health`、`/api/v1/experiment/trigger`、`/api/v1/experiment/execute`、`/api/v1/experiment/status`。

- [ ] **Step 4: 手动验证模板和概览**

用 stub platform 发布模板，刷新页面统计。

## Task 9: 旧数据导入、状态持久化和收尾

**Files:**
- Create: `src/smartaccess/runtime/application/migration_service.py`
- Create: `src/smartaccess/desktop/pages/settings_page.py` 或集成到右侧上下文栏
- Modify: `src/smartaccess/desktop/shell/main_window.py`

- [ ] **Step 1: 实现旧 workspace 导入**

从 `workspace` 复制 anchors、workflows、templates 到 `workspace_v2`，加载验证失败的文件跳过并记录日志。

- [ ] **Step 2: 完成 UI 状态持久化**

保存和恢复窗口大小、最大化、导航栏、右侧上下文栏、页面 splitter。

- [ ] **Step 3: 全面手动检查待办项**

逐项验证 `to do(1).txt` 中的优化点。

- [ ] **Step 4: 运行核心验证命令**

运行：

```powershell
$env:PYTHONPATH="src"
python -m compileall src/smartaccess
python run_desktop.py
```

预期：编译无语法错误，桌面能启动。

## 自审记录

- 覆盖 spec 所列所有功能域。
- 明确了允许修改范围。
- 等待动作、独立 workspace、浅色 UI、日志、布局持久化均有任务。
- 没有安排大面积测试；如需正式测试，会在对应实现阶段先确认。
