# Instrument Archetypes Memory

- `scope`: 仪器画像抽象和接入时需要关注的稳定要素。
- `source_of_truth`: `docs/PRD.zh-CN.md`, `docs/contracts/interfaces.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `instrument_profile.yaml`

## 画像要素

- 窗口签名：标题、尺寸、主要控件布局。
- 锚点类型：按钮、输入框、状态条、图表区、告警区。
- 动作能力：允许点击、输入、快捷键、等待条件。
- 安全限制：参数边界、手动确认点、禁止动作。

## 接入要求

- 新仪器必须先产出最小可用画像。
- 画像必须能支持窗口定位、步骤执行和状态观察三类需求。
