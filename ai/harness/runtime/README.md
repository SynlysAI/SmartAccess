# Runtime Harness

## 目标

定义 SmartAccess 运行时 AI 组件如何被装配、调用和审计。

## 装配方式

- 输入契约：`workflow.yaml`、`anchors.yaml`、`platform_adapter.yaml`
- 运行代理：orchestrator、executor、observer、recovery
- 支撑能力：runtime memory、runtime skills、事件日志写入器

## 样例运行链路

1. 加载工作流与锚点集。
2. orchestrator 校验步骤、锚点和动作能力。
3. executor 按步骤执行动作。
4. observer 在需要 OCR 判断时裁剪 observe region 并轮询文本匹配。
5. 无 OCR 预期时，orchestrator 执行默认等待。
6. recovery 在异常时接管并写入恢复事件。
7. 平台适配层同步状态、日志和 trace 事实。

## 审计要求

- 每个动作、等待策略、OCR 事实和异常都应进入 `run_trace.jsonl`。
- 每次恢复动作必须带异常类型和处理结果。
- 平台同步失败也必须产生本地事件。
- OCR 结果自动进入 trace。

## 验收门槛

- 能覆盖首次锚点配置、正常执行、OCR 命中、OCR 超时、无观测默认等待、异常恢复、平台回传七类主链路。
- 不允许绕过安全限制执行高风险动作。
- 不允许 v2 主路径依赖旧的复杂绑定、手工结果声明、自由判断或多模式识别。
