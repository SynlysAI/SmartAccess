---
name: vision-calibrator
description: Calibrate SmartAccess ROI regions and visual recognition patterns for instrument software. Use whenever the task involves screenshot regions, OCR bindings, anchor marking, or validating whether the observer can reliably detect state.
---

# Vision Calibrator

## 触发条件

- 需要标注 ROI 或验证视觉识别可靠性。
- 需要把截图区域绑定到状态字段或工作流步骤。
- 需要处理窗口尺寸、分辨率、DPI 或布局变化导致的坐标漂移。

## 输入

- 仪器界面截图
- 仪器画像草稿
- 目标状态或读数清单

## 输出

- ROI 定义，包括 absolute ROI 和 normalized ROI
- 视觉模式建议（OCR / presence / template / color / none）
- 坐标鲁棒性与窗口比例漂移风险提示

## 执行步骤

1. 识别关键读数区、状态区、动作目标和告警区。
2. 为每个区域定义命名、类型、识别方式和用途。
3. 同时保存 absolute ROI 和 normalized ROI，用 normalized ROI 适配窗口尺寸变化。
4. 为关键动作选择视觉反馈策略：OCR 用于动态文字，presence 用于元素出现，template 用于稳定图标，color 用于状态色，none 用于纯动作目标。
5. 把 ROI 与工作流步骤、condition 和平台字段绑定。
6. 标记容易误识别的区域和替代方案。

## 提示词与界面文案规则

- 面向用户的接入建议必须描述可验证的结果，例如“建议锚点”“识别方式”“需要人工确认”，避免开发者调试说明。
- 生成设备画像时，输出必须严格匹配 SmartAccess `InstrumentProfileContract`；不能自动保存或覆盖用户当前配置。
- ROI 建议必须同时说明 absolute ROI 与 normalized ROI；缺少截图坐标时，明确要求用户标注，不要编造精确坐标。
- Provider 名称只在配置、状态或错误定位场景出现；普通流程说明使用“AI 辅助接入”或“设备接入建议”。
- 高风险动作、颜色/模板基准和 OCR 低置信度场景必须提示人工复核。

## 失败处理

- 如果界面元素不稳定，建议增加多重观测或人工确认点。
- 如果 OCR 不可靠，优先建议模板匹配或状态存在性判断。
