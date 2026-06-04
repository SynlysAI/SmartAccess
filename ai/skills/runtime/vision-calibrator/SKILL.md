---
name: vision-calibrator
description: Calibrate SmartAccess ROI regions and visual recognition patterns for instrument software. Use whenever the task involves screenshot regions, OCR bindings, anchor marking, or validating whether the observer can reliably detect state.
---

# Vision Calibrator

## 触发条件

- 需要标注 ROI 或验证视觉识别可靠性。
- 需要把截图区域绑定到状态字段或工作流步骤。

## 输入

- 仪器界面截图
- 仪器画像草稿
- 目标状态或读数清单

## 输出

- ROI 定义
- 视觉模式建议
- 可靠性风险提示

## 执行步骤

1. 识别关键读数区、状态区和告警区。
2. 为每个区域定义命名、识别方式和用途。
3. 把 ROI 与工作流步骤和平台字段绑定。
4. 标记容易误识别的区域和替代方案。

## 失败处理

- 如果界面元素不稳定，建议增加多重观测或人工确认点。
- 如果 OCR 不可靠，优先建议模板匹配或状态存在性判断。
