# Eval Harness

## 目标

定义 SmartAccess 关键场景的回归评测方式，确保文档、契约和运行时设计能互相映射。

## 评测范围

- 工作流生成
- 首次仪器接入
- UI 执行
- OCR/状态识别
- 异常恢复
- 平台同步

## 评测维度

- 场景覆盖度
- 契约完整性
- 关键状态流转正确性
- 失败处理是否可追溯

## 验收门槛

- 五个关键场景全部有 eval case。
- 每个 eval case 都能指向相关 memory、skill、agent、contract。
- 任何新增仪器接入都必须补充或复用 eval case。
