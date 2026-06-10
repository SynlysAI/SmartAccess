# 微信演示配置说明

本文档说明仓库内的微信桌面端演示资产，覆盖动作原语、观测条件、识别模式，以及如何在 SmartAccess 桌面端复测。

## 资产清单

设备画像位于 `workspace/instruments/weixin_01/instrument_profile.yaml`，窗口签名为标题包含“微信”，截图尺寸基准为 1311 x 1150。

演示草稿位于 `workspace/workflows/`：

- `wf_wechat_basic_actions`：以 click、double_click、type、press_enter、hotkey、wait 为主，只在搜索结果和会话打开两个关键节点使用 wait_until。
- `wf_wechat_ocr_wait`：演示 OCR + wait_until，等待搜索结果出现联系人文本。
- `wf_wechat_template_match`：演示 template + screenshot_check，校验搜索结果头像区域。
- `wf_wechat_color_presence`：演示 presence + color，等待会话出现并检查发送按钮状态色。
- `wf_wechat_screenshot_check`：演示一次性截图校验，串联 OCR 与 template。

标准模板位于 `workspace/templates/wf_wechat_send_test_standard/`，其中 `1.0.1` 覆盖 OCR、template、presence、color 与发送动作，可直接在“运行监控”里复测。

## 动作原语

`click` 在目标锚点 ROI 中心单击一次。它适合搜索框、联系人结果、发送按钮等明确控件。执行前由 profile 的窗口签名定位微信窗口，执行后进入下一步；如果锚点被标记为人工确认或触发安全规则，会先阻塞等待确认。

`double_click` 在目标锚点中心连续双击。微信演示中用于快速打开联系人结果；如果本机微信单击即可打开，也可以改回 `click`。

`type` 会先聚焦目标锚点，再输入 `value`。搜索联系人和输入消息都使用这个动作。`value` 可以是中文字符串，运行 trace 会记录动作类型和目标。

`press_enter` 向当前焦点发送 Enter。它不一定需要 target；如果要明确作用到输入框，可先用 `click` 聚焦 `文本输入`。

`hotkey` 发送组合键，`value` 采用 `ctrl+a`、`ctrl+s` 这类文本形式。微信演示里用 `ctrl+a` 选择输入框内已有文本。

`wait` 是固定等待，`value` 单位是秒。它只适合短暂界面过渡；需要等待 UI 状态变化时应优先用 `wait_until`。

`wait_until` 会按 `condition.source` 指向的 ROI 周期截图和识别，直到 `operator` 判断通过或超过 `timeout_seconds`。常用字段包括 `mode`、`operator`、`expected`、`timeout_seconds` 和 `poll_interval_seconds`。微信 OCR 等待流程用它等待 `用户确认` 包含联系人名。

`screenshot_check` 截图一次并对指定 source 做条件判断。它适合模板、颜色、OCR 的即时校验；失败会阻止步骤成功，运行监控会显示 readings、min confidence 和截图路径。

## 识别模式

`ocr` 用于读取 ROI 内文字。微信演示的 `用户确认` 锚点读取搜索结果联系人名称，条件示例为 `operator: contains`、`expected: 黄亚男`。

`template` 用于和预存模板图比较。锚点 `联系人头像模板` 配置了 `vision_config.template_asset_path` 和 `template_threshold`。运行结果通常显示 `matched` 或 `no_match`，confidence 是匹配分数。

`color` 用于判断区域颜色是否接近基准色。锚点 `发送按钮颜色` 使用 `color_reference_hex: '#07c160'` 与 `color_tolerance: 0.18`，可判断发送按钮是否进入可点击状态。

`presence` 用于判断区域是否出现可见前景。锚点 `会话存在` 使用 `presence_threshold: 0.01` 判断聊天会话标题/消息区是否存在，结果通常为 `present` 或 `missing`。

## 复测路径

1. 打开 SmartAccess 桌面端，进入“设备接入与校准”，双击加载 `weixin_01`。
2. 确认微信窗口已打开，必要时重新捕获截图并微调 ROI。
3. 进入“工作流设计”，选择任一 `wf_wechat_*` 草稿，检查 ROI 绑定和输出项。
4. 对 `wait_until` 或 `screenshot_check` 步骤点击条件按钮，确认 source、mode、operator、expected、timeout_seconds 可读。
5. 进入“模板库”，可看到 `wf_wechat_send_test_standard` 的模板版本；删除任意版本都会先弹出确认。
6. 进入“运行监控”，选择演示流程发起运行。左侧时间线会换行显示步骤详情，右侧观测结果会展示 OCR/template/color/presence 的结构化 readings。

## 调整建议

联系人名和消息文本在 workflow YAML 的 `value`/`expected` 字段中。更换演示对象时，只需要同步修改搜索输入值和 OCR expected。

如果微信窗口缩放或分辨率变化较大，优先在校准页重新捕获截图并保存 profile。保存时会同时写入 pixel ROI 与 normalized ROI，后续运行会更稳定。
