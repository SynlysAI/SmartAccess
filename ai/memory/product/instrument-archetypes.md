# Instrument Archetypes Memory

- `scope`: 锚点集抽象和接入时需要关注的稳定要素。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-19
- `related_contracts`: `anchors.yaml`

## 锚点集要素

- 设备 ID：新建设备接入主键，必须使用 `体系-实验室-产品型号-设备编号` 四段格式。
- 窗口签名：标题、进程、截图尺寸和主要布局线索。
- 动作区域：按钮、输入框、可聚焦控件等 `action_region`。
- 观测区域：动作后需要 OCR 判断时使用的可选 `observe_region`。
- 动作能力：每个锚点声明 `supported_actions`。
- 默认等待：无 OCR 预期时使用 `default_wait_seconds`。

## 接入要求

- 新仪器必须先产出最小可用 `anchors.yaml`。
- 新建设备的 `anchors.yaml.profile_id` 必须等于四段设备 ID；历史旧 profile 仅作为加载兼容，不作为新示例。
- 锚点集必须能支持窗口定位、步骤执行和 OCR 观察三类需求。
- 锚点配置不保存运行结果、手工结果声明、视觉基准或识别阈值。
