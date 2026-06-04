# Glossary Memory

- `scope`: SmartAccess 仓库统一术语和模块命名。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `workflow.yaml`, `instrument_profile.yaml`, `platform_adapter.yaml`, `run_trace.jsonl`, `eval_case.yaml`

## 术语

- `SpecLabOS`: 实验管理平台，SmartAccess 的平台对接对象。
- `workflow`: 实验工作流配置，描述步骤、前置条件和输出。
- `instrument profile`: 仪器画像，描述窗口签名、锚点、动作能力和安全限制。
- `platform adapter`: 平台适配配置，定义 API 地址和字段映射。
- `run trace`: 运行轨迹日志，记录动作、观测、结果和产物。
- `runtime harness`: 运行时装配约束。
- `eval harness`: 回归评测约束。

## 命名要求

- 对外文档统一使用 `SmartAccess`。
- 平台对象统一使用 `SpecLabOS`。
- 禁止同义词混用，例如把 `instrument profile` 写成多个无定义别名。
