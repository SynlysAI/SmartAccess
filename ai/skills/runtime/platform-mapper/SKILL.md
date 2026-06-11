---
name: platform-mapper
description: Map SmartAccess local workflow metadata, run status, and run trace facts to SpecLabOS API contracts. Use whenever a task requires `platform_adapter.yaml`, field mapping, endpoint mapping, or upload/retry design.
---

# Platform Mapper

## 触发条件

- 需要配置平台对接。
- 需要新增或调整本地字段到平台字段的映射。
- 需要从 `run_trace.jsonl` 提取 OCR 事实或执行状态上传平台。

## 输入

- 本地 workflow metadata。
- `run_trace.jsonl` 步骤级事实。
- 平台接口约束。
- 运行状态与日志需求。

## 输出

- `platform_adapter.yaml` 草稿。
- 字段映射说明。
- trace 提取规则。
- 重试与补传建议。

## 执行步骤

1. 识别本地 workflow metadata、run status 和 trace 字段。
2. 定义 endpoint 和 payload 映射。
3. 将 `anchor_profile` 映射到平台所需字段；如平台仍要求旧字段名，只在适配器中转换。
4. 明确平台结果字段来自哪一步的 `actual_text`、`matched`、`status` 或截图路径。
5. 增加重试、缓存和补传策略。

## 失败处理

- 如果平台字段定义缺失，保留占位并显式标记待确认项。
- 禁止把敏感认证信息直接写入样例文档。
- 禁止要求用户在 workflow 中新增手工结果声明来满足平台上传；应从 trace 提取。
