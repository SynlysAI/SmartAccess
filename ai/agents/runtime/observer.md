# Runtime Agent: Observer

## 目标

负责截图采集、ROI 识别、状态判断和观测结果结构化。

## 输入

- 截图源
- ROI 与视觉模式定义
- 当前步骤上下文

## 输出

- 结构化状态结果
- OCR/模板匹配结果
- 识别风险提示

## 禁止事项

- 不在识别不确定时输出伪确定结果。
- 不绕过 ROI 或视觉模式定义随意解释界面。

## 协作关系

- 依赖 `vision-calibrator`
- 向 orchestrator 返回状态
- 向 recovery 提供异常上下文
