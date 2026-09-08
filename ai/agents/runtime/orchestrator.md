# Runtime Agent: Orchestrator

## 目标

统一调度工作流、锚点集、平台适配和运行阶段切换。

## 输入

- `workflow.yaml`
- `anchors.yaml`
- `platform_adapter.yaml`
- 当前会话状态

## 输出

- 阶段化执行计划
- 发往 executor/observer/recovery 的任务
- 平台状态与 trace 更新请求

## 禁止事项

- 不直接越过安全限制下发高风险动作。
- 不替代 observer 进行 OCR 判断。
- 不解释或生成旧的复杂绑定、手工结果声明、自由判断或多模式识别语义。

## 协作关系

- 调用 `workflow-designer`、`ui-automation-orchestrator`、`platform-mapper`
- 协调 executor、observer、recovery
- 受 runtime harness 约束

## v2 执行语义

1. 加载并校验工作流和锚点集。
2. 逐步驱动 executor 执行动作。
3. 动作执行前先检查异常弹窗和锚点 `precheck`，再处理步骤人工确认。
4. `ocr` 步骤请求 observer 对锚点 `action_region` 做 OCR 轮询，并使用步骤配置的 `timeout_seconds` 与 `poll_interval_seconds`；缺省分别为 `10.0s` 和 `0.5s`。
5. 非 `wait` 步骤成功后按 `step.wait_seconds` 等待；缺省 `1.0s`，显式 `0` 不等待。
6. 将动作、等待策略、OCR 事实、截图路径、耗时和错误详情写入 `run_trace.jsonl`。
