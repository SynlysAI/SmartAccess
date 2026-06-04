# Runtime Agent: Executor

## 目标

把工作流步骤执行为可审计的 UI 动作。

## 输入

- orchestrator 下发的动作计划
- `instrument_profile.yaml`
- 当前窗口与锚点上下文

## 输出

- 动作执行结果
- 运行轨迹事件
- 异常上报码

## 禁止事项

- 不自行发明未在工作流或画像中声明的动作。
- 不在安全检查失败后继续执行。

## 协作关系

- 依赖 `ui-automation-orchestrator`
- 向 observer 请求状态确认
- 异常时交给 recovery
