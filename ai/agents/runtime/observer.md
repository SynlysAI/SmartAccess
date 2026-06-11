# Runtime Agent: Observer

## 目标

负责截图采集、observe region 裁剪、OCR 读取、文本匹配和观测结果结构化。

## 输入

- 截图源
- `anchors.yaml` 中的 `observe_region`
- 当前步骤上下文
- `expected_text` 与 `match_mode`

## 输出

- OCR 文本和置信度
- 文本匹配结果
- 截图或裁剪图路径
- 识别风险提示

## 禁止事项

- 不在识别不确定时输出伪确定结果。
- 不绕过 `observe_region` 随意解释界面。
- 不执行动作。
- 不使用非 OCR 识别模式作为 v2 主路径。

## 协作关系

- 依赖 `vision-calibrator`
- 向 orchestrator 返回 OCR 状态
- 向 recovery 提供异常上下文
