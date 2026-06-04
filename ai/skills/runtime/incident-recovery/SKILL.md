---
name: incident-recovery
description: Recover SmartAccess runs when UI automation, vision recognition, or platform sync fails. Use whenever an execution session becomes blocked, a step needs retry/rollback/manual confirmation, or recovery policy must be applied.
---

# Incident Recovery

## 触发条件

- 运行进入 `Blocked` 状态。
- OCR、窗口定位、平台同步或安全检查失败。

## 输入

- 当前 `run_trace.jsonl`
- 异常分类
- 恢复规则 memory

## 输出

- 恢复动作建议
- 是否需要人工确认
- 恢复后的状态记录

## 执行步骤

1. 识别异常类型和影响范围。
2. 选择重试、回退、重新校准、人工确认或终止策略。
3. 把恢复动作写入运行轨迹。
4. 若恢复成功，将会话返回到可继续状态。

## 失败处理

- 超过重试阈值时强制升级。
- 遇到安全条件不满足时禁止继续执行。
