---
name: vision-calibrator
description: Calibrate SmartAccess anchor target regions and optional pre-action visual-check regions. Use for screenshot marking, anchor calibration, image/text prechecks, or validating whether an action target is safe before execution.
---

# Vision Calibrator

## 触发条件

- 需要标注锚点目标区域或执行前校验区域。
- 需要配置图像一致、文字一致或图像加文字校验。
- 需要处理窗口尺寸、分辨率、DPI 或布局变化导致的坐标漂移。

## 输入

- 仪器界面截图。
- 锚点集草稿。
- 目标动作或目标 OCR 文本清单。

## 输出

- `anchors.yaml` 所需锚点定义。
- 每个锚点的 `action_region` 和可选 `precheck.region`，均包含 pixel 与 normalized 坐标。
- 坐标鲁棒性与窗口比例漂移风险提示。

## 执行步骤

1. 识别关键按钮、输入框和可聚焦控件，为每个目标定义稳定的 `id`。
2. 保存 `action_region` 的 pixel 与 normalized 坐标。
3. 需要防止点错窗口或位置时，添加 `precheck`，校验区域默认与目标区域一致。
4. 按内容选择 `image`、`text` 或 `image_text`；图像阈值默认 `0.8`。
5. 文字校验只用于包含稳定可读文字的区域；大小写和 NFKC 归一化由后台固定处理。
6. 人工确认只在工作流步骤中配置，不写入锚点。

## 提示词与界面文案规则

- 面向用户的接入建议必须描述可验证的结果，例如“建议锚点”“目标区域”“执行前校验区域”，避免开发者调试说明。
- 生成锚点集时，输出必须严格匹配 SmartAccess `AnchorProfileContract`；不能自动保存或覆盖用户当前配置。
- ROI 建议必须同时说明 pixel 与 normalized 坐标；缺少截图坐标时，明确要求用户标注，不要编造精确坐标。
- Provider 名称只在配置、状态或错误定位场景出现；普通流程说明使用“AI 辅助接入”或“锚点建议”。
- 高风险动作必须建议在工作流步骤启用执行前确认。

## 失败处理

- 如果界面元素不稳定，建议调整目标区域或执行前校验区域。
- 如果文字校验不可靠，优先使用图像一致或图像加文字校验。

## 能力样例校准提示

- 串口调试助手 UDP：优先校准“打开/关闭服务”按钮状态区域和收发日志区域；不同工具布局差异大，示例坐标只能作为模板。
- Windows 计算器：结果显示区应完整覆盖大号数字，聚焦锚点只需稳定落在计算器窗口可点击区域。
