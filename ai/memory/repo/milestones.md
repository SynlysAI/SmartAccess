# Milestones Memory

- `scope`: SmartAccess 产品与架构基线阶段目标。
- `source_of_truth`: `docs/PRD.zh-CN.md`
- `last_reviewed`: 2026-06-19
- `related_contracts`: `anchors.yaml`, `workflow.yaml`, `run_trace.jsonl`, `eval_case.yaml`

## 阶段目标

### 基线阶段

- 建立完整 PRD、架构和契约体系。
- 建立 runtime/repo 两套 AI 组件目录和模板。
- 建立关键场景回归用例骨架。

### VER1：可视化监控、模板版本和动作识别闭环（2026-06-09）

- 运行监控形成左侧时间线 + 右侧观测/审计/日志标签页。
- 模板库具备查找、状态过滤、版本时间线、基础更新/删除和切换发布版本式回滚。
- 早期工作流设计曾尝试加入绑定、手工结果声明和步骤级观测闭环。
- 校准与执行开始使用 normalized ROI 处理窗口尺寸变化下的坐标映射。
- 项目新增 `documentation-sync` skill，要求每次重要改动同步功能日志、PRD、SPEC、契约、README、memory 和 skill。

### VER2：锚点 -> 工作流 -> 执行断代简化（2026-06-11）

- 主导航收敛为 `锚点`、`工作流`、`模板/平台`、`执行` 四个一级页面。
- 公开契约改为 `anchors.yaml`、简化 `workflow.yaml` 和步骤级 `run_trace.jsonl`。
- 删除手工结果声明、复杂绑定、自由判断、独立等待动作、截图校验动作和多模式识别。
- Observer/VisionProvider 收敛为 OCR-only：截图、裁剪、OCR 读取、文本匹配。
- 平台结果从 `run_trace.jsonl` 的 OCR 事实提取，旧平台字段名只允许在适配器映射。

### VER3：能力示例与监控审计增强（2026-06-11）

- 运行监控步骤时间线和审计区支持长文本查看，截图、trace、workflow、anchors 产物引用以可点击路径展示。
- 工作流 AI 助手输入框默认保持为空，只保留 placeholder 引导。
- 受版本控制的能力示例增加 `serial_debug_assistant_udp` 和 `windows_calculator`。
- Eval harness 从 5 个关键场景扩展为 7 个关键场景。

### VER4：运行监控设备摘要与 OCR 日志审计（2026-06-15）

- 运行监控页在工作流选择区展示绑定锚点集/设备摘要，包括窗口签名、锚点数量、OCR 观测锚点数量和动作能力。
- OCR 观测事件进入运行日志时显式打印 pass 规则、实际识别文本、匹配结果和尝试次数；结构化 trace 契约不变。
- 多行说明/审计/日志区域开始使用富文本层级，至少区分标题、字段名、正文和错误/警告状态。
- OCR mismatch 的 `run.failed` 事件携带当前 OCR 规则与识别结果，运行日志可直接高亮失败原因，不需要打开 trace 才能定位。
- 运行监控摘要和日志以可读性优先：摘要字段分块换行，日志按当前宽度自动换行，不再依赖横向滚动查看长 OCR 调试信息。

### VER5：设备 ID、输入模式与运行日志边界（2026-06-19）

- 新建设备 ID 收敛为 `体系-实验室-产品型号-设备编号` 四段主键规则，作为 `anchors.yaml` 的 `profile_id` 和 workflow 的 `anchor_profile` 引用。
- 历史旧锚点文件保持加载兼容；严格校验只作用于新建设备接入 UI 和后端创建路径。
- `type` 步骤新增 `free` 自由输入和 `incrementing` 运行内递增输入；递增值在 run session 内从 `001` 开始，下一次运行重新计数。
- `RunSession` 增加设备 ID、作者和工作流名称上下文；运行日志在开始与结束事件输出 START/END 边界。
- trace 的 `action.value` 记录运行时真实输入值，原始 workflow 不被运行时回写修改。

### MVP 阶段

- 打通 1 到 3 类 Windows 仪器接入。
- 实现锚点配置、线性工作流执行、OCR 观测、平台 trace 同步和异常恢复闭环。

### V1 阶段

- 增强 Linux、多窗口、模板管理和更复杂调度能力。
