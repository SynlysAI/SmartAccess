# Milestones Memory

- `scope`: SmartAccess 产品与架构基线阶段目标。
- `source_of_truth`: `docs/PRD.zh-CN.md`
- `last_reviewed`: 2026-06-09
- `related_contracts`: `eval_case.yaml`

## 阶段目标

### 基线阶段

- 建立完整 PRD、架构和契约体系。
- 建立 runtime/repo 两套 AI 组件目录和模板。
- 建立关键场景回归用例骨架。

### MVP 阶段

- 打通 1 到 3 类 Windows 仪器接入。
- 实现工作流执行、状态识别、平台同步和异常恢复闭环。

### VER1：可视化监控、模板版本和动作识别闭环（2026-06-09）

- 运行监控形成左侧时间线 + 右侧观测/审计/日志标签页。
- 模板库具备查找、状态过滤、版本时间线、基础更新/删除和切换发布版本式回滚。
- 工作流设计明确 `roi_bindings` 和 `outputs` 的语义，并开始使用步骤级 `condition` 形成动作后观测闭环。
- 校准与执行开始使用 normalized ROI 处理窗口尺寸变化下的坐标映射。
- 项目新增 `documentation-sync` skill，要求每次重要改动同步功能日志、PRD、SPEC、契约、README、memory 和 skill。

### V1 阶段

- 增强 Linux、多窗口、模板管理和更复杂调度能力。
