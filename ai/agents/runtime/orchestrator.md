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
3. 若步骤有 `expected_text` 或 `match_mode == not_empty`，请求 observer 对锚点 `observe_region` 做 OCR 轮询。
4. 若无 OCR 判断，按 `step.wait_seconds -> anchor.default_wait_seconds -> app default 2.0s` 等待。
5. 将动作、等待策略、OCR 事实、截图路径、耗时和错误详情写入 `run_trace.jsonl`。
