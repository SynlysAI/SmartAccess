# Runtime Harness

## 目标

定义 SmartAccess 运行时 AI 组件如何被装配、调用和审计。

## 装配方式

- 输入契约：`workflow.yaml`、`instrument_profile.yaml`、`platform_adapter.yaml`
- 运行代理：orchestrator、executor、observer、recovery
- 支撑能力：runtime memory、runtime skills、事件日志写入器

## 样例运行链路

1. 加载工作流与仪器画像。
2. orchestrator 生成执行阶段计划。
3. executor 按阶段执行动作。
4. observer 在关键节点采样并判断状态。
5. recovery 在异常时接管并写入恢复事件。
6. 平台适配层同步状态和结果。

## 审计要求

- 每个动作和观测都应进入 `run_trace.jsonl`。
- 每次恢复动作必须带异常类型和处理结果。
- 平台同步失败也必须产生本地事件。

## 验收门槛

- 能覆盖首次接入、正常执行、状态识别、异常恢复、平台回传五类主链路。
- 不允许绕过安全限制执行高风险动作。
