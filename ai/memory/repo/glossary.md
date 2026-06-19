# Glossary Memory

- `scope`: SmartAccess 仓库统一术语和模块命名。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/architecture/system-overview.md`
- `last_reviewed`: 2026-06-19
- `related_contracts`: `anchors.yaml`, `workflow.yaml`, `platform_adapter.yaml`, `run_trace.jsonl`, `eval_case.yaml`

## 术语

- `SpecLabOS`: 实验管理平台，SmartAccess 的平台对接对象。
- `anchor profile`: 锚点集，描述窗口签名、动作区域、可选 OCR 观测区域和动作能力。
- `device_id`: 新建设备接入主键，采用 `体系-实验室-产品型号-设备编号` 四段格式，同时作为 `anchors.yaml.profile_id`。
- `workflow`: 实验工作流配置，描述线性步骤、锚点引用、动作和 OCR 预期。
- `input_mode`: `type` 步骤的输入模式，取值为 `free` 或 `incrementing`。
- `increment_rule`: 每个 `type + incrementing` 步骤独立保存的递增式输入规则，默认模式为 `{device_id}-{author}-{date}-{counter:03d}`，计数状态按 `workflow_id + sequence_key` 持久化。
- `platform adapter`: 平台适配配置，定义 API 地址和字段映射。
- `run trace`: 运行轨迹日志，记录每步动作、等待策略、OCR 事实、结果和产物。
- `run boundary`: 运行日志中的 START/END 边界，包含设备 ID、作者、工作流名称和 session。
- `runtime harness`: 运行时装配约束。
- `eval harness`: 回归评测约束。

## 命名要求

- 对外文档统一使用 `SmartAccess`。
- 平台对象统一使用 `SpecLabOS`。
- v2 对外契约统一使用 `anchor profile` / `anchors.yaml`，不再使用 `instrument profile` 作为主契约名称。
- 新建设备 ID 写法必须稳定为 `体系-实验室-产品型号-设备编号`，不要再用 `d1`、`device_01` 作为新建设备示例。
- 禁止同义词混用，例如把 `anchor profile` 写成多个无定义别名。
