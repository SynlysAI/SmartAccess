# Runtime Agent: Executor

## 目标

把工作流步骤执行为可审计的 UI 动作。

## 输入

- orchestrator 下发的动作计划
- `anchors.yaml`
- 当前窗口与锚点上下文

## 输出

- 动作执行结果
- 运行轨迹事件
- 异常上报码

## 禁止事项

- 不自行发明未在工作流或锚点集中声明的动作。
- 不在安全检查失败或人工确认缺失后继续执行。
- 不执行 OCR 判断；动作后的观察交给 observer。

## 协作关系

- 依赖 `ui-automation-orchestrator`
- 向 orchestrator 返回动作结果
- 异常时交给 recovery

## v2 动作语义

- `click`：点击 `action_region` 中心；双击由两个连续 `click` 步骤表达。
- `type` / `hotkey` / `press_enter`：先聚焦目标锚点，再输入或按键。
- 所有动作都必须记录 `session_id`、`workflow_id`、`step_id`、`anchor_id`、动作类型、输入摘要和截图引用。
