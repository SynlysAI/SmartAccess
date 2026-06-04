---
name: readme-maintainer
description: Keep the SmartAccess README usable as the main developer entry point. Use whenever repo structure, core docs, onboarding instructions, or instrument-extension workflow changes.
---

# README Maintainer

## 触发条件

- 仓库结构变化。
- 新增核心文档或 AI 组件目录。
- 新增仪器接入流程或开发顺序发生变化。

## 输入

- README
- 当前目录结构
- PRD 与架构文档

## 输出

- 更新后的 README
- 新人可读的入口说明
- 断链或失效说明清单

## 执行步骤

1. 确认 README 仍能解释产品是什么、不是什么。
2. 校验核心链接和目录说明。
3. 校验新增仪器接入步骤与当前文档一致。

## 失败处理

- 如果 README 与 PRD 冲突，优先对齐 PRD 和架构文档再回写 README。
