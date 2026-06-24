# SmartAccess AI 文字模型与多模态模型分离配置设计

## 背景

SmartAccess 当前 AI 相关能力通过单组环境变量 `SMARTACCESS_AI_PROVIDER/BASE_URL/MODEL/API_KEY/TIMEOUT_SECONDS/USER_AGENT` 配置，由 `bootstrap/runtime.py` 的 `_build_ai_generator` 装配成**单个** `SmartAccessAiGenerator` 实例，同时供给：

- `WorkflowService`（用于 AI 生成工作流，仅文字输入）
- `RuntimeFacade.ai_generator`（用于 AI 辅助接入设备，需要识别截图）

两个用途对模型能力的要求相反：

| 用途 | 是否需要图片识别 | 适合的模型 |
| --- | --- | --- |
| AI 生成工作流 | 否 | 纯文字 LLM（如 DeepSeek）|
| AI 辅助接入 | 是 | 多模态模型（如 Codex / GPT 系列）|

当前单组配置只能选其一，无法同时发挥文字 LLM 的成本与速度优势和多模态模型的视觉理解能力。`.env` 里现有两组被注释/启用的写法也反映出用户已经手动在两套模型之间切换，正是这次改造要消除的痛点。

项目早期还规划过一套 `SMARTACCESS_AI_PROFILES` 多档案 + 用途绑定的机制（见 `README.md` 与 `tests/integration/test_services.py`），但 src 侧从未落地（`workspace_settings.py` 模块不存在，`facade.py` 没有相关方法）。本设计**不沿用** profile 抽象，原因见「设计取舍 / 为何不引入 profile 机制」。

## 目标

1. `.env` 同时配置两套独立的 AI 模型：一套文字 LLM、一套多模态模型。
2. 后端按"当前调用是否需要图片识别"自动选择对应模型，调用方不感知。
3. AI 生成工作流始终使用文字 LLM；AI 辅助接入始终使用多模态模型。
4. 保留旧的单组 `SMARTACCESS_AI_*` 配置写法作为向后兼容 fallback，老 `.env` 不破坏。
5. `SmartAccessAiGenerator` 的 `supports_images` / wire_api 选择逻辑保持不变（继续按 `provider` 名推断）。

## 非目标

1. **不引入 profile 抽象**——不增加 `SMARTACCESS_AI_PROFILES`、用途绑定变量、运行时切换 UI 等。
2. **不修改 `SmartAccessAiGenerator` 的内部协议**（`supports_images` / `draft_workflow` / `draft_instrument_profile` 签名不变）。
3. **不修复 `tests/integration/test_services.py` 中既有的 profile 相关测试**——这些测试依赖 src 里从未实现的 `workspace_settings` 模块，与本次改造正交，保持现状。
4. **不持久化"用途 → 模型"偏好**——只用环境变量静态绑定。
5. **不引入 `SMARTACCESS_AI_PROFILE_{ID}_WIRE_API` 字段**——wire_api 继续由 `provider` 名推断（codex→responses，其他→chat_completions）。

## 总体架构

```text
.env
  ├─ SMARTACCESS_AI_TEXT_*      （文字 LLM 配置）
  ├─ SMARTACCESS_AI_VISION_*    （多模态配置）
  └─ SMARTACCESS_AI_USER_AGENT  （共享）

settings.py
  ├─ ai_text_provider/base_url/model/api_key/timeout_seconds
  └─ ai_vision_provider/base_url/model/api_key/timeout_seconds
       │
       ↓ from_env() 读取，兼容旧 SMARTACCESS_AI_* 单组写法
       │
bootstrap/runtime.py
  ├─ _build_text_ai_generator()   → SmartAccessAiGenerator | None
  └─ _build_vision_ai_generator() → SmartAccessAiGenerator | None
       │                  │
       ↓                  ↓
WorkflowService       RuntimeFacade
(draft_generator      (ai_generator
 = text generator)     = vision generator)
       │                  │
       ↓                  ↓
  AI 生成工作流        AI 辅助接入
  (文字输入)           (截图 + 文字)
```

## 详细设计

### `.env` 配置形态

```dotenv
# === AI 模型配置 ===
SMARTACCESS_AI_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36

# 文字 LLM —— 用于 AI 生成工作流（不需要图片识别）
SMARTACCESS_AI_TEXT_PROVIDER=deepseek
SMARTACCESS_AI_TEXT_BASE_URL=https://api.deepseek.com/v1
SMARTACCESS_AI_TEXT_MODEL=deepseek-v4-pro
SMARTACCESS_AI_TEXT_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS=60

# 多模态 —— 用于 AI 辅助接入（需要识别截图）
SMARTACCESS_AI_VISION_PROVIDER=codex
SMARTACCESS_AI_VISION_BASE_URL=https://code.ppchat.vip/v1
SMARTACCESS_AI_VISION_MODEL=gpt-5.4
SMARTACCESS_AI_VISION_API_KEY=sk-yyyyyyyyyyyyyyyyyyyyyyyyyyyy
SMARTACCESS_AI_VISION_TIMEOUT_SECONDS=60

# === 向后兼容（仅当 TEXT_* / VISION_* 都未配时生效）===
# 旧单组写法：TEXT 和 VISION 都使用同一组配置
# SMARTACCESS_AI_PROVIDER=codex
# SMARTACCESS_AI_BASE_URL=https://code.ppchat.vip/v1
# SMARTACCESS_AI_MODEL=gpt-5.4
# SMARTACCESS_AI_API_KEY=sk-yyyyyyyyyyyyyyyyyyyyyyyyyyyy
# SMARTACCESS_AI_TIMEOUT_SECONDS=60
```

### `settings.py` 数据结构

新增 10 个字段，分两组：

```python
class AppSettings(BaseModel):
    # ... 既有字段保留 ...
    ai_user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)

    # 新增：TEXT 用途（工作流生成）
    ai_text_provider: str = Field(default="template")
    ai_text_base_url: str = Field(default="https://fufei.mossx.ai/v1")
    ai_text_model: str = Field(default="GPT-5.4")
    ai_text_api_key: str | None = Field(default=None)
    ai_text_timeout_seconds: float = Field(default=30.0, gt=0)

    # 新增：VISION 用途（设备接入）
    ai_vision_provider: str = Field(default="template")
    ai_vision_base_url: str = Field(default="https://fufei.mossx.ai/v1")
    ai_vision_model: str = Field(default="GPT-5.4")
    ai_vision_api_key: str | None = Field(default=None)
    ai_vision_timeout_seconds: float = Field(default=30.0, gt=0)

    # 旧字段保留：ai_provider / ai_api_key / ai_base_url / ai_model /
    # ai_timeout_seconds / deepseek_* —— 不再单独使用，仅作为 fallback 数据源
```

#### `from_env` 读取优先级

对 TEXT 组：

1. 任一 `SMARTACCESS_AI_TEXT_*` 存在 → 读 `SMARTACCESS_AI_TEXT_*`
2. 否则若 `SMARTACCESS_AI_PROVIDER` 存在 → 从旧单组字段读（`SMARTACCESS_AI_PROVIDER/BASE_URL/MODEL/API_KEY/TIMEOUT_SECONDS`）
3. 否则若 `DEEPSEEK_*` 存在 → 从更早期的 `DEEPSEEK_*` 字段读（保留旧 fallback）
4. 都没有 → `ai_text_provider="template"`（AI 不启用）

VISION 组同 TEXT。

#### 共享字段

`SMARTACCESS_AI_USER_AGENT` 仍由两组共用，不拆分。

### `bootstrap/runtime.py` 装配

`_build_ai_generator` 拆成两个独立函数：

```python
def _build_text_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """装配文字 LLM 生成器，用于 AI 生成工作流。

    Args:
        settings: 应用配置。

    Returns:
        文字 LLM 生成器；未配置或 provider=template 时返回 None。
    """

    provider = settings.ai_text_provider.lower().strip()
    if provider == "template":
        return None
    if not settings.ai_text_api_key:
        get_logger().warning(
            "Text AI provider=%s 未配置 API Key，工作流 AI 生成未启用", provider
        )
        return None
    return SmartAccessAiGenerator(
        api_key=settings.ai_text_api_key,
        base_url=settings.ai_text_base_url,
        model=settings.ai_text_model,
        provider=provider,
        timeout_seconds=settings.ai_text_timeout_seconds,
        user_agent=settings.ai_user_agent,
    )


def _build_vision_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """装配多模态生成器，用于 AI 辅助接入。

    Args:
        settings: 应用配置。

    Returns:
        多模态生成器；未配置或 provider=template 时返回 None。
    """

    provider = settings.ai_vision_provider.lower().strip()
    if provider == "template":
        return None
    if not settings.ai_vision_api_key:
        get_logger().warning(
            "Vision AI provider=%s 未配置 API Key，AI 辅助接入未启用", provider
        )
        return None
    return SmartAccessAiGenerator(
        api_key=settings.ai_vision_api_key,
        base_url=settings.ai_vision_base_url,
        model=settings.ai_vision_model,
        provider=provider,
        timeout_seconds=settings.ai_vision_timeout_seconds,
        user_agent=settings.ai_user_agent,
    )
```

`build_runtime_facade` 内：

```python
text_ai_generator = _build_text_ai_generator(settings)
vision_ai_generator = _build_vision_ai_generator(settings)

workflows = WorkflowService(
    workspace_dir=settings.workspace_dir,
    anchors=anchors,
    draft_generator=text_ai_generator,   # 工作流 AI 走文字 LLM
)
# ...
return RuntimeFacade(
    # ... 其他参数 ...
    ai_generator=vision_ai_generator,    # 设备接入 AI 走多模态
)
```

### `facade.py` 改动

`RuntimeFacade.__init__` 的 `ai_generator` 参数语义明确为"设备接入用的多模态生成器"，**不需要改方法签名**。受影响方法：

- `draft_instrument_from_prompt()` —— 走 vision generator（已是当前实现，只是数据源变了）
- `ai_label()` / `ai_reasoning()` —— 仍基于 `self._ai_generator`（即 vision generator）返回

`draft_workflow_from_prompt()` 委托给 `self._workflows.draft_from_prompt()`，`WorkflowService` 已经装配了 text generator，无需 facade 介入。

### `SmartAccessAiGenerator` 改动

**不动**。`supports_images` 继续按 `provider == "codex"` 推断。`draft_workflow` / `draft_instrument_profile` 的 wire_api 选择继续按 provider 名分支。

### 兼容性矩阵

| 配置场景 | TEXT 行为 | VISION 行为 |
| --- | --- | --- |
| 仅配 `SMARTACCESS_AI_TEXT_*` / `_VISION_*` | 使用 TEXT 配置 | 使用 VISION 配置 |
| 仅配旧 `SMARTACCESS_AI_*` 单组 | fallback 到旧配置 | fallback 到旧配置（与 TEXT 同源）|
| 仅配更早期 `DEEPSEEK_*` | fallback 到 DEEPSEEK 配置 | fallback 到 DEEPSEEK 配置 |
| 都未配 | `provider=template`，不启用 | `provider=template`，不启用 |
| 配了 TEXT 但没配 VISION | 使用 TEXT 配置 | fallback 到旧配置 → 若旧配置也没有则不启用 |

## 设计取舍

### 为何不引入 profile 机制

`README.md` 与 `tests/integration/test_services.py` 曾规划过 `SMARTACCESS_AI_PROFILES` 多档案 + `AI_PROFILE_WORKFLOW`/`AI_PROFILE_DEVICE_ONBOARDING` 用途绑定 + UI 持久化偏好的方案，但 src 侧从未实现。本次改造考虑过后选择**不沿用**，原因：

1. **YAGNI**：当前只有两个用途（工作流生成、设备接入），且能力需求明确（文字 vs 多模态）。引入 profile 抽象和用途映射反而增加阅读成本。
2. **配置直观**：`SMARTACCESS_AI_TEXT_*` / `_VISION_*` 直接对应"文字模型"和"多模态模型"，用户无需理解 profile 概念。
3. **代码简洁**：不需要新增 `workspace_settings.py` 模块、不需要 facade 增加路由方法、不需要修改测试。
4. **既有的 profile 测试保持现状**：那部分测试本来就是 src 未实现导致的 ImportError 状态，与本次改造正交，未来若真有需求再单独立项。

### 为何保留旧 `SMARTACCESS_AI_*` 字段作 fallback

1. 现有部署的 `.env` 文件不需要同步改造，升级零成本。
2. `.envexample` 默认值仍可工作。
3. 测试文件中可能存在直接构造 `AppSettings` 用旧字段的代码——保留可避免大面积改测试。

### 为何不引入 `SUPPORTS_IMAGES` 显式字段

`SmartAccessAiGenerator.supports_images` 当前按 `provider == "codex"` 硬判断，本设计保留该机制：

1. 项目当前用到的多模态 provider 就是 codex 一种，硬判断足够。
2. 若未来增加其他多模态 provider（如 claude、gemini），统一改为白名单或显式字段是独立的小重构，与本次配置改造解耦。
3. 不增加用户的配置项数量。

## 影响范围

### 必改文件

1. `.env` —— 改成两组 TEXT/VISION 配置
2. `.envexample` —— 同步示例和注释
3. `src/smartaccess/shared/config/settings.py` —— 加 10 个字段、改 `from_env` 读取逻辑
4. `src/smartaccess/bootstrap/runtime.py` —— 拆 `_build_text_ai_generator` + `_build_vision_ai_generator`，调整 `build_runtime_facade` 装配
5. `README.md` —— 更新 AI 相关环境变量说明

### 可选改动

6. `docs/recent-updates-2026-06-24.md` —— 新增本次改造说明（如该项目有近期更新文档惯例）

### 不改文件

- `src/smartaccess/runtime/adapters/ai_generator.py` —— `SmartAccessAiGenerator` 协议和实现不变
- `src/smartaccess/runtime/application/facade.py` —— 方法签名不变，仅装配数据源变化
- `tests/integration/test_ai_generator_transport.py` —— 直接构造 `SmartAccessAiGenerator`，与配置无关
- `tests/integration/test_services.py` —— 既有 profile 测试保持原状

## 验证策略

1. **单元测试**：为 `AppSettings.from_env` 新增用例覆盖：
   - 仅配 `SMARTACCESS_AI_TEXT_*` / `_VISION_*` 的读取
   - 仅配旧 `SMARTACCESS_AI_*` 时 TEXT 和 VISION 都回退到同一组
   - 都未配时 provider 为 `template`
2. **集成验证**：本地启动后：
   - 调用 AI 生成工作流 → 日志显示 deepseek/text provider
   - 调用 AI 辅助接入 → 日志显示 codex/vision provider
3. **回归验证**：保留旧 `.env` 单组写法启动，确认两个 AI 功能仍能正常工作（虽然共用同一模型）。
