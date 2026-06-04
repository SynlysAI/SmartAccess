# Project Context Memory

- `scope`: SmartAccess 仓库级背景、定位和交付阶段。
- `source_of_truth`: `README.md`, `docs/PRD.zh-CN.md`
- `last_reviewed`: 2026-06-04
- `related_contracts`: `docs/contracts/interfaces.md`

## 核心结论

- 本仓库当前是产品与架构基线，不是已完成代码实现。
- 产品主路径是 `PyQt 桌面端 + UI 自动化 + 视觉识别 + SpecLabOS/FastAPI`。
- 部署优先实验室内网，可接外部模型，但必须有本地替代预案。

## 使用说明

- 任何新文档都应先对齐本文件中的产品定位。
- 若主形态或部署策略变化，应优先更新本文件和 PRD。
