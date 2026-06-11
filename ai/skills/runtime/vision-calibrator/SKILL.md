---
name: vision-calibrator
description: Calibrate SmartAccess v2 anchor action regions and optional OCR observation regions for instrument software. Use whenever the task involves screenshot regions, anchor marking, OCR observation binding, or validating whether the observer can reliably read text.
---

# Vision Calibrator

## 触发条件

- 需要标注锚点 action region 或 OCR observe region。
- 需要把截图区域绑定到工作流步骤的动作后 OCR 判断。
- 需要处理窗口尺寸、分辨率、DPI 或布局变化导致的坐标漂移。

## 输入

- 仪器界面截图。
- 锚点集草稿。
- 目标动作或目标 OCR 文本清单。

## 输出

- `anchors.yaml` 所需锚点定义。
- 每个锚点的 `action_region` 和可选 `observe_region`，均包含 pixel 与 normalized 坐标。
- 坐标鲁棒性与窗口比例漂移风险提示。

## 执行步骤

1. 识别关键动作目标、输入框、按钮和动作后需要读取的文本区域。
2. 为每个锚点定义 `id`、`label`、`supported_actions` 和 `default_wait_seconds`。
3. 保存 `action_region` 的 pixel 与 normalized 坐标。
4. 如果动作后需要 OCR 判断，保存一个 `observe_region`。
5. 标记容易误识别、容易遮挡或需要人工确认的区域。
6. 输出前确认没有视觉基准、识别阈值或自由区域绑定。

## 提示词与界面文案规则

- 面向用户的接入建议必须描述可验证的结果，例如“建议锚点”“动作区域”“观测区域”“需要人工确认”，避免开发者调试说明。
- 生成锚点集时，输出必须严格匹配 SmartAccess v2 `AnchorProfileContract`；不能自动保存或覆盖用户当前配置。
- ROI 建议必须同时说明 pixel 与 normalized 坐标；缺少截图坐标时，明确要求用户标注，不要编造精确坐标。
- Provider 名称只在配置、状态或错误定位场景出现；普通流程说明使用“AI 辅助接入”或“锚点建议”。
- 高风险动作和 OCR 低置信度场景必须提示人工复核。

## 失败处理

- 如果界面元素不稳定，建议放大 action/observe 区域或增加人工确认点。
- 如果 OCR 不可靠，优先建议调整 observe region、等待时机或人工确认；不要退回非 OCR 识别方案。

## 能力样例校准提示

- 串口调试助手 UDP：优先校准“打开/关闭服务”按钮状态区域和收发日志区域；不同工具布局差异大，示例坐标只能作为模板。
- Windows 计算器：结果显示区应完整覆盖大号数字，聚焦锚点只需稳定落在计算器窗口可点击区域。
