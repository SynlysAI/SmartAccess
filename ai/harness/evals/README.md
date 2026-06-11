# Eval Harness

## 目标

定义 SmartAccess 关键场景的回归评测方式，确保文档、契约和运行时设计能互相映射。

## 评测范围

- 锚点集创建
- 工作流生成
- UI 执行
- OCR 命中与超时
- 无观测默认等待
- 停止/取消中断轮询
- 异常恢复
- 平台模板与 trace 同步
- 串口调试助手 UDP 服务打开/发送
- Windows 计算器运算与 OCR 结果证明

## 评测维度

- 场景覆盖度
- 契约完整性
- 关键状态流转正确性
- 失败处理是否可追溯
- 旧字段是否已从主路径删除

## 验收门槛

- 七个关键场景全部有 eval case。
- 每个 eval case 都能指向相关 memory、skill、agent、contract。
- 契约测试覆盖 `anchors.yaml`、简化 `workflow.yaml` 和步骤级 `run_trace.jsonl`。
- 运行测试覆盖 OCR 命中成功、OCR 超时失败、无观测默认等待、缺失锚点失败、停止中断轮询。
- 任何新增仪器接入都必须补充或复用 eval case。
