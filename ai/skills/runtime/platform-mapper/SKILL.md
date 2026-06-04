---
name: platform-mapper
description: Map SmartAccess local workflow fields, status, and run outputs to SpecLabOS API contracts. Use whenever a task requires `platform_adapter.yaml`, field mapping, endpoint mapping, or upload/retry design.
---

# Platform Mapper

## 触发条件

- 需要配置平台对接。
- 需要新增或调整本地字段到平台字段的映射。

## 输入

- 本地工作流输出
- 平台接口约束
- 运行状态与日志需求

## 输出

- `platform_adapter.yaml` 草稿
- 字段映射说明
- 重试与补传建议

## 执行步骤

1. 识别本地输出字段和平台目标字段。
2. 定义 endpoint 和 payload 映射。
3. 增加重试、缓存和补传策略。
4. 明确哪些字段来自 OCR、日志或人工输入。

## 失败处理

- 如果平台字段定义缺失，保留占位并显式标记待确认项。
- 禁止把敏感认证信息直接写入样例文档。
