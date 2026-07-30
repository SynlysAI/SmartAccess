# AI 文字模型与多模态模型分离配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单组 `SMARTACCESS_AI_*` 配置拆成 `SMARTACCESS_AI_TEXT_*`（文字 LLM）和 `SMARTACCESS_AI_VISION_*`（多模态）两组，让 AI 生成工作流使用文字 LLM、AI 辅助接入使用多模态，同时保留旧单组写法作向后兼容 fallback。

**Architecture:** `settings.py` 新增 10 个字段（`ai_text_*` / `ai_vision_*` 各 5 个），`from_env` 按三级优先级读取（TEXT/VISION 专用变量 → 旧单组 `SMARTACCESS_AI_*` → 早期 `DEEPSEEK_*`）。`bootstrap/runtime.py` 把 `_build_ai_generator` 拆成 `_build_text_ai_generator` + `_build_vision_ai_generator`，`WorkflowService.draft_generator` 装 text、`RuntimeFacade.ai_generator` 装 vision。`SmartAccessAiGenerator` 协议不动。

**Tech Stack:** Python 3.14 + pydantic（settings）、pytest（测试，仅 `AppSettings.from_env` 写测试，遵循用户 CLAUDE.md "只写核心代码测试" 规则）。

**Spec:** `docs/superpowers/specs/2026-06-24-ai-text-vision-models-design.md`

---

## File Structure

### 修改文件

| 文件 | 责任 | 改动 |
| --- | --- | --- |
| `src/smartaccess/shared/config/settings.py` | 应用配置 | 加 10 个字段、改 `from_env` 读取逻辑 |
| `src/smartaccess/bootstrap/runtime.py` | 运行时装配 | 拆 `_build_text_ai_generator` + `_build_vision_ai_generator`、调整 `build_runtime_facade` |
| `.env` | 项目本地配置 | 改成 TEXT/VISION 两组 |
| `.envexample` | 配置示例 | 同步示例 |
| `README.md` | 项目文档 | 更新 AI 环境变量说明 |

### 新增文件

| 文件 | 责任 |
| --- | --- |
| `tests/integration/test_settings_ai_text_vision.py` | `AppSettings.from_env` 读取逻辑的单元测试 |

### 不动文件

- `src/smartaccess/runtime/adapters/ai_generator.py` —— `SmartAccessAiGenerator` 协议不变
- `src/smartaccess/runtime/application/facade.py` —— 方法签名不变，仅装配数据源变化
- `tests/integration/test_ai_generator_transport.py` —— 直接构造 generator，与配置无关
- 其他 broken 测试文件（`test_services.py`、`test_facade.py` 等）—— 与本次改造正交

---

## Task 1: 在 `settings.py` 加 `ai_text_*` / `ai_vision_*` 字段

**Files:**
- Modify: `src/smartaccess/shared/config/settings.py:28-37`（在现有 `ai_*` 字段块后追加）
- Test: `tests/integration/test_settings_ai_text_vision.py`（新建）

**说明：** 本任务只加字段定义和默认值，**不改 `from_env`**。下一步任务才接通读取逻辑。这种拆分让"字段存在且有默认值"和"从环境变量读取"独立可测。

- [ ] **Step 1: 写测试覆盖新字段的默认值**

创建 `tests/integration/test_settings_ai_text_vision.py`：

```python
"""AppSettings 新增 ai_text_* / ai_vision_* 字段的单元测试。"""

from __future__ import annotations

import pytest

from smartaccess.shared.config.settings import AppSettings


def test_settings_default_ai_text_fields() -> None:
    """未传任何 AI 配置时，ai_text_* 字段取默认值。"""

    settings = AppSettings()
    assert settings.ai_text_provider == "template"
    assert settings.ai_text_base_url == "https://fufei.mossx.ai/v1"
    assert settings.ai_text_model == "GPT-5.4"
    assert settings.ai_text_api_key is None
    assert settings.ai_text_timeout_seconds == 30.0


def test_settings_default_ai_vision_fields() -> None:
    """未传任何 AI 配置时，ai_vision_* 字段取默认值。"""

    settings = AppSettings()
    assert settings.ai_vision_provider == "template"
    assert settings.ai_vision_base_url == "https://fufei.mossx.ai/v1"
    assert settings.ai_vision_model == "GPT-5.4"
    assert settings.ai_vision_api_key is None
    assert settings.ai_vision_timeout_seconds == 30.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: FAIL，错误信息包含 `AttributeError: ... has no attribute 'ai_text_provider'`（字段尚未定义）。

注：若系统 python 没装 pytest，使用项目 conda 环境（参考用户 CLAUDE.md "python环境依赖" 节）；后续所有 `pytest` 命令同理。

- [ ] **Step 3: 在 `AppSettings` 类里追加 10 个字段**

编辑 `src/smartaccess/shared/config/settings.py`，找到现有的 `ai_timeout_seconds` 字段行（约 32 行）：

```python
    ai_timeout_seconds: float = Field(default=30.0, gt=0)
    ai_user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)
    deepseek_api_key: str | None = Field(default=None)
```

在 `ai_user_agent` 后面、`deepseek_api_key` 前面插入 10 个新字段：

```python
    ai_timeout_seconds: float = Field(default=30.0, gt=0)
    ai_user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)
    ai_text_provider: str = Field(default="template")
    ai_text_base_url: str = Field(default="https://fufei.mossx.ai/v1")
    ai_text_model: str = Field(default="GPT-5.4")
    ai_text_api_key: str | None = Field(default=None)
    ai_text_timeout_seconds: float = Field(default=30.0, gt=0)
    ai_vision_provider: str = Field(default="template")
    ai_vision_base_url: str = Field(default="https://fufei.mossx.ai/v1")
    ai_vision_model: str = Field(default="GPT-5.4")
    ai_vision_api_key: str | None = Field(default=None)
    ai_vision_timeout_seconds: float = Field(default=30.0, gt=0)
    deepseek_api_key: str | None = Field(default=None)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: PASS（2 个测试用例全绿）。

- [ ] **Step 5: Commit**

```bash
git add src/smartaccess/shared/config/settings.py tests/integration/test_settings_ai_text_vision.py
git commit -m "新增 AppSettings 的 ai_text_* / ai_vision_* 字段定义"
```

---

## Task 2: `from_env` 读取 `SMARTACCESS_AI_TEXT_*` / `_VISION_*` 专用变量

**Files:**
- Modify: `src/smartaccess/shared/config/settings.py`（`from_env` 方法内的 `cls(...)` 构造调用）
- Test: `tests/integration/test_settings_ai_text_vision.py`（追加用例）

**说明：** 本任务接通新字段的"专用变量读取"路径，但**不**做旧变量 fallback。Fallback 在 Task 3 处理。

- [ ] **Step 1: 追加测试覆盖专用变量读取**

在 `tests/integration/test_settings_ai_text_vision.py` 末尾追加：

```python
def test_from_env_reads_text_and_vision_specific_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """from_env 应分别读取 SMARTACCESS_AI_TEXT_* 和 _VISION_* 专用变量。"""

    for key in (
        "SMARTACCESS_AI_PROVIDER",
        "SMARTACCESS_AI_BASE_URL",
        "SMARTACCESS_AI_MODEL",
        "SMARTACCESS_AI_API_KEY",
        "SMARTACCESS_AI_TIMEOUT_SECONDS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMARTACCESS_AI_TEXT_PROVIDER", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_API_KEY", "sk-text-key")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS", "60")

    monkeypatch.setenv("SMARTACCESS_AI_VISION_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_BASE_URL", "https://code.ppchat.vip/v1")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_MODEL", "gpt-5.4")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_API_KEY", "sk-vision-key")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_TIMEOUT_SECONDS", "90")

    settings = AppSettings.from_env()

    assert settings.ai_text_provider == "deepseek"
    assert settings.ai_text_base_url == "https://api.deepseek.com/v1"
    assert settings.ai_text_model == "deepseek-v4-pro"
    assert settings.ai_text_api_key == "sk-text-key"
    assert settings.ai_text_timeout_seconds == 60.0

    assert settings.ai_vision_provider == "codex"
    assert settings.ai_vision_base_url == "https://code.ppchat.vip/v1"
    assert settings.ai_vision_model == "gpt-5.4"
    assert settings.ai_vision_api_key == "sk-vision-key"
    assert settings.ai_vision_timeout_seconds == 90.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py::test_from_env_reads_text_and_vision_specific_vars -v`

Expected: FAIL，断言失败（当前 `from_env` 不读这些变量，新字段保留默认值）。

- [ ] **Step 3: 在 `from_env` 内追加专用变量读取并传给构造器**

编辑 `src/smartaccess/shared/config/settings.py` 的 `from_env` 方法。

在现有 `ai_timeout` 局部变量定义（约 79-82 行）之后追加：

```python
        ai_timeout = _get(
            "SMARTACCESS_AI_TIMEOUT_SECONDS",
            _get("DEEPSEEK_TIMEOUT_SECONDS", "30"),
        )

        ai_text_provider = _get("SMARTACCESS_AI_TEXT_PROVIDER", "template") or "template"
        ai_text_base_url = _get(
            "SMARTACCESS_AI_TEXT_BASE_URL",
            "https://fufei.mossx.ai/v1",
        )
        ai_text_model = _get("SMARTACCESS_AI_TEXT_MODEL", "GPT-5.4") or "GPT-5.4"
        ai_text_api_key = _get("SMARTACCESS_AI_TEXT_API_KEY")
        ai_text_timeout_raw = _get("SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS", "30") or "30"

        ai_vision_provider = _get("SMARTACCESS_AI_VISION_PROVIDER", "template") or "template"
        ai_vision_base_url = _get(
            "SMARTACCESS_AI_VISION_BASE_URL",
            "https://fufei.mossx.ai/v1",
        )
        ai_vision_model = _get("SMARTACCESS_AI_VISION_MODEL", "GPT-5.4") or "GPT-5.4"
        ai_vision_api_key = _get("SMARTACCESS_AI_VISION_API_KEY")
        ai_vision_timeout_raw = _get("SMARTACCESS_AI_VISION_TIMEOUT_SECONDS", "30") or "30"
```

然后在 `return cls(...)` 构造调用里，在 `ai_user_agent=...` 后追加 10 个传参：

```python
            ai_user_agent=(
                _get("SMARTACCESS_AI_USER_AGENT", DEFAULT_AI_USER_AGENT)
                or DEFAULT_AI_USER_AGENT
            ),
            ai_text_provider=ai_text_provider,
            ai_text_base_url=ai_text_base_url or "https://fufei.mossx.ai/v1",
            ai_text_model=ai_text_model,
            ai_text_api_key=ai_text_api_key,
            ai_text_timeout_seconds=float(ai_text_timeout_raw),
            ai_vision_provider=ai_vision_provider,
            ai_vision_base_url=ai_vision_base_url or "https://fufei.mossx.ai/v1",
            ai_vision_model=ai_vision_model,
            ai_vision_api_key=ai_vision_api_key,
            ai_vision_timeout_seconds=float(ai_vision_timeout_raw),
            deepseek_api_key=_get("DEEPSEEK_API_KEY"),
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: PASS（3 个测试用例全绿）。

- [ ] **Step 5: Commit**

```bash
git add src/smartaccess/shared/config/settings.py tests/integration/test_settings_ai_text_vision.py
git commit -m "from_env 读取 SMARTACCESS_AI_TEXT_* 与 _VISION_* 专用变量"
```

---

## Task 3: `from_env` 加 fallback —— TEXT/VISION 未配时回退到旧 `SMARTACCESS_AI_*` 单组变量

**Files:**
- Modify: `src/smartaccess/shared/config/settings.py`（Task 2 写的局部变量块）
- Test: `tests/integration/test_settings_ai_text_vision.py`（追加用例）

**说明：** 优先级：`SMARTACCESS_AI_TEXT_*` → `SMARTACCESS_AI_*` → `DEEPSEEK_*` → 默认值。本任务接通中间一级。

- [ ] **Step 1: 追加测试覆盖 fallback 到旧单组变量**

在 `tests/integration/test_settings_ai_text_vision.py` 末尾追加：

```python
def test_from_env_falls_back_to_legacy_single_group_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEXT/VISION 专用变量未配时，应回退到旧 SMARTACCESS_AI_* 单组变量。

    旧 .env 只有一组 SMARTACCESS_AI_* 时，TEXT 和 VISION 都使用它，
    保证现有部署升级后行为不变。
    """

    for key in (
        "SMARTACCESS_AI_TEXT_PROVIDER",
        "SMARTACCESS_AI_TEXT_BASE_URL",
        "SMARTACCESS_AI_TEXT_MODEL",
        "SMARTACCESS_AI_TEXT_API_KEY",
        "SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_VISION_PROVIDER",
        "SMARTACCESS_AI_VISION_BASE_URL",
        "SMARTACCESS_AI_VISION_MODEL",
        "SMARTACCESS_AI_VISION_API_KEY",
        "SMARTACCESS_AI_VISION_TIMEOUT_SECONDS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMARTACCESS_AI_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("SMARTACCESS_AI_MODEL", "legacy-model")
    monkeypatch.setenv("SMARTACCESS_AI_API_KEY", "sk-legacy")
    monkeypatch.setenv("SMARTACCESS_AI_TIMEOUT_SECONDS", "45")

    settings = AppSettings.from_env()

    # TEXT 和 VISION 都回退到旧单组配置
    assert settings.ai_text_provider == "codex"
    assert settings.ai_text_base_url == "https://legacy.example/v1"
    assert settings.ai_text_model == "legacy-model"
    assert settings.ai_text_api_key == "sk-legacy"
    assert settings.ai_text_timeout_seconds == 45.0

    assert settings.ai_vision_provider == "codex"
    assert settings.ai_vision_base_url == "https://legacy.example/v1"
    assert settings.ai_vision_model == "legacy-model"
    assert settings.ai_vision_api_key == "sk-legacy"
    assert settings.ai_vision_timeout_seconds == 45.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py::test_from_env_falls_back_to_legacy_single_group_vars -v`

Expected: FAIL（当前 TEXT 字段会读默认 `"template"`，断言 `== "codex"` 失败）。

- [ ] **Step 3: 把 Task 2 写的 10 个局部变量块改成 fallback 链**

编辑 `src/smartaccess/shared/config/settings.py`，把 Task 2 加入的局部变量块替换为带 fallback 的版本：

```python
        legacy_provider = _get("SMARTACCESS_AI_PROVIDER", "template") or "template"
        legacy_base_url = ai_base_url or "https://fufei.mossx.ai/v1"
        legacy_model = ai_model or "GPT-5.4"
        legacy_api_key = _get("SMARTACCESS_AI_API_KEY", _get("DEEPSEEK_API_KEY"))
        legacy_timeout = ai_timeout or "30"

        ai_text_provider = _get("SMARTACCESS_AI_TEXT_PROVIDER", legacy_provider) or legacy_provider
        ai_text_base_url = _get("SMARTACCESS_AI_TEXT_BASE_URL", legacy_base_url)
        ai_text_model = _get("SMARTACCESS_AI_TEXT_MODEL", legacy_model) or legacy_model
        ai_text_api_key = _get("SMARTACCESS_AI_TEXT_API_KEY", legacy_api_key)
        ai_text_timeout_raw = _get("SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS", legacy_timeout) or legacy_timeout

        ai_vision_provider = _get("SMARTACCESS_AI_VISION_PROVIDER", legacy_provider) or legacy_provider
        ai_vision_base_url = _get("SMARTACCESS_AI_VISION_BASE_URL", legacy_base_url)
        ai_vision_model = _get("SMARTACCESS_AI_VISION_MODEL", legacy_model) or legacy_model
        ai_vision_api_key = _get("SMARTACCESS_AI_VISION_API_KEY", legacy_api_key)
        ai_vision_timeout_raw = _get("SMARTACCESS_AI_VISION_TIMEOUT_SECONDS", legacy_timeout) or legacy_timeout
```

注意 `ai_base_url` / `ai_model` / `ai_timeout` 这三个变量在 `from_env` 前面已经按 `SMARTACCESS_AI_*` → `DEEPSEEK_*` → 默认值的链式 fallback 计算好了（见 settings.py:71-82），直接复用即可，无需重复 fallback 逻辑。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: PASS（4 个测试用例全绿，包括 Task 2 那个——因为专用变量优先级更高，fallback 不影响它）。

- [ ] **Step 5: Commit**

```bash
git add src/smartaccess/shared/config/settings.py tests/integration/test_settings_ai_text_vision.py
git commit -m "from_env 为 TEXT/VISION 字段加旧 SMARTACCESS_AI_* 单组 fallback"
```

---

## Task 4: `from_env` 加最终 fallback —— 进一步回退到 `DEEPSEEK_*`

**Files:**
- Modify: `src/smartaccess/shared/config/settings.py`（不需要改，验证即可）
- Test: `tests/integration/test_settings_ai_text_vision.py`（追加用例）

**说明：** 因为 Task 3 直接复用了 `ai_base_url` / `ai_model` / `ai_timeout`，这三个变量在 `from_env` 前面已经按 `SMARTACCESS_AI_*` → `DEEPSEEK_*` → 默认值做了 fallback（见 settings.py:71-82），所以 `DEEPSEEK_*` 这一级 fallback **应该已经天然生效**。本任务只补测试确认行为，不再改代码。

- [ ] **Step 1: 追加测试覆盖 DEEPSEEK_* fallback**

在 `tests/integration/test_settings_ai_text_vision.py` 末尾追加：

```python
def test_from_env_falls_back_to_deepseek_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既未配 TEXT/VISION 也未配 SMARTACCESS_AI_* 时，回退到 DEEPSEEK_*。

    早期 .env 只配了 DEEPSEEK_* 这一组，仍需保持向后兼容。
    """

    for key in (
        "SMARTACCESS_AI_TEXT_PROVIDER",
        "SMARTACCESS_AI_TEXT_BASE_URL",
        "SMARTACCESS_AI_TEXT_MODEL",
        "SMARTACCESS_AI_TEXT_API_KEY",
        "SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_VISION_PROVIDER",
        "SMARTACCESS_AI_VISION_BASE_URL",
        "SMARTACCESS_AI_VISION_MODEL",
        "SMARTACCESS_AI_VISION_API_KEY",
        "SMARTACCESS_AI_VISION_TIMEOUT_SECONDS",
        "SMARTACCESS_AI_PROVIDER",
        "SMARTACCESS_AI_BASE_URL",
        "SMARTACCESS_AI_MODEL",
        "SMARTACCESS_AI_API_KEY",
        "SMARTACCESS_AI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_TIMEOUT_SECONDS", "20")

    settings = AppSettings.from_env()

    # TEXT 和 VISION 的 api_key/base_url/model/timeout 都从 DEEPSEEK_* 回退
    assert settings.ai_text_api_key == "sk-deepseek"
    assert settings.ai_text_base_url == "https://api.deepseek.com"
    assert settings.ai_text_model == "deepseek-chat"
    assert settings.ai_text_timeout_seconds == 20.0
    # provider 没有 DEEPSEEK_PROVIDER 变量，回退到默认 "template"
    assert settings.ai_text_provider == "template"

    assert settings.ai_vision_api_key == "sk-deepseek"
    assert settings.ai_vision_base_url == "https://api.deepseek.com"
    assert settings.ai_vision_model == "deepseek-chat"
    assert settings.ai_vision_timeout_seconds == 20.0
    assert settings.ai_vision_provider == "template"
```

- [ ] **Step 2: 运行测试**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py::test_from_env_falls_back_to_deepseek_vars -v`

Expected: PASS（因为 Task 3 已经通过复用 `ai_base_url`/`ai_model`/`ai_timeout` 间接接通了 DEEPSEEK_* fallback，且 `ai_text_api_key` 也通过 `_get("SMARTACCESS_AI_API_KEY", _get("DEEPSEEK_API_KEY"))` 链回退）。

- [ ] **Step 3: 如果测试失败，补丁 `from_env`**

如果 Step 2 失败（例如 `ai_text_provider` 没有正确回退），把 Task 3 写的 `legacy_provider` 改成：

```python
        legacy_provider = _get("SMARTACCESS_AI_PROVIDER") or "template"
```

去掉对 `"template"` 默认值的依赖，让 `_get` 自己返回 None 时再 fallback。但通常 Step 2 会通过，本步骤是防御性补丁。

- [ ] **Step 4: 再次运行全部测试**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: PASS（5 个测试用例全绿）。

- [ ] **Step 5: Commit（仅当 Step 3 改了代码）**

```bash
git add src/smartaccess/shared/config/settings.py tests/integration/test_settings_ai_text_vision.py
git commit -m "from_env 补全 TEXT/VISION 字段的 DEEPSEEK_* fallback"
```

若 Step 3 未触发，仅提交新增测试：

```bash
git add tests/integration/test_settings_ai_text_vision.py
git commit -m "补充 DEEPSEEK_* fallback 的 settings 单元测试"
```

---

## Task 5: `bootstrap/runtime.py` 拆出 `_build_text_ai_generator` + `_build_vision_ai_generator`

**Files:**
- Modify: `src/smartaccess/bootstrap/runtime.py:360-385`（替换 `_build_ai_generator`）

**说明：** `_build_ai_generator` 是模块私有函数，没有现有测试覆盖（`test_facade.py` 已 broken、`test_services.py` 已 broken）。按用户 CLAUDE.md "只写核心代码测试" 的规则，装配类私有函数的测试可以省略——通过 Task 6 的装配验证间接覆盖。本任务不写新测试，但要在 Step 4 手动 import 验证函数能正常调用。

- [ ] **Step 1: 把 `_build_ai_generator` 替换成两个独立函数**

编辑 `src/smartaccess/bootstrap/runtime.py:360-385`，删除整个 `_build_ai_generator` 函数，替换为：

```python
def _build_text_ai_generator(settings: AppSettings) -> SmartAccessAiGenerator | None:
    """装配文字 LLM 生成器，用于 AI 生成工作流。

    Args:
        settings: 应用配置。

    Returns:
        文字 LLM 生成器；provider=template 或未配 API Key 时返回 None。
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
        多模态生成器；provider=template 或未配 API Key 时返回 None。
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

- [ ] **Step 2: 修改 `build_runtime_facade` 的装配语句**

编辑 `src/smartaccess/bootstrap/runtime.py`，找到第 62 行：

```python
    ai_generator = _build_ai_generator(settings)
```

替换为两行：

```python
    text_ai_generator = _build_text_ai_generator(settings)
    vision_ai_generator = _build_vision_ai_generator(settings)
```

然后找到第 64-68 行的 `WorkflowService` 装配：

```python
    workflows = WorkflowService(
        workspace_dir=settings.workspace_dir,
        anchors=anchors,
        draft_generator=ai_generator,
    )
```

把 `draft_generator=ai_generator` 改为 `draft_generator=text_ai_generator`：

```python
    workflows = WorkflowService(
        workspace_dir=settings.workspace_dir,
        anchors=anchors,
        draft_generator=text_ai_generator,
    )
```

然后找到第 117 行的 `RuntimeFacade` 装配里：

```python
        ai_generator=ai_generator,
```

改为：

```python
        ai_generator=vision_ai_generator,
```

- [ ] **Step 3: 检查无语法错误**

Run: `python -c "import sys; sys.path.insert(0, 'src'); from smartaccess.bootstrap.runtime import _build_text_ai_generator, _build_vision_ai_generator, build_runtime_facade; print('ok')"`

Expected: 输出 `ok`。

- [ ] **Step 4: 手动验证两个装配函数对默认 settings 的行为**

Run:
```bash
python -c "import sys; sys.path.insert(0, 'src'); from smartaccess.shared.config.settings import AppSettings; from smartaccess.bootstrap.runtime import _build_text_ai_generator, _build_vision_ai_generator; s = AppSettings(); print('text:', _build_text_ai_generator(s)); print('vision:', _build_vision_ai_generator(s))"
```

Expected: 两个都输出 `text: None` 和 `vision: None`（因为默认 provider='template'）。

- [ ] **Step 5: Commit**

```bash
git add src/smartaccess/bootstrap/runtime.py
git commit -m "拆分 _build_text_ai_generator 与 _build_vision_ai_generator"
```

---

## Task 6: 验证 `build_runtime_facade` 装配数据源正确

**Files:**
- Test: `tests/integration/test_settings_ai_text_vision.py`（追加装配验证用例）

**说明：** 通过装配后检查 `WorkflowService._draft_generator` 和 `RuntimeFacade._ai_generator` 的 `provider` 属性，验证 text/vision 分别装到了正确的位置。这是 spec 验证策略第 2 条（"AI 生成工作流走 text provider，AI 辅助接入走 vision provider"）的自动化版本。

- [ ] **Step 1: 追加装配验证测试**

在 `tests/integration/test_settings_ai_text_vision.py` 末尾追加：

```python
def test_build_runtime_facade_routes_text_and_vision_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """build_runtime_facade 应把 text generator 装给 WorkflowService，
    把 vision generator 装给 RuntimeFacade.ai_generator。"""

    for key in (
        "SMARTACCESS_AI_PROVIDER",
        "SMARTACCESS_AI_BASE_URL",
        "SMARTACCESS_AI_MODEL",
        "SMARTACCESS_AI_API_KEY",
        "SMARTACCESS_AI_TIMEOUT_SECONDS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMARTACCESS_AI_TEXT_PROVIDER", "deepseek")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_API_KEY", "sk-text-key")
    monkeypatch.setenv("SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS", "60")

    monkeypatch.setenv("SMARTACCESS_AI_VISION_PROVIDER", "codex")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_BASE_URL", "https://code.ppchat.vip/v1")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_MODEL", "gpt-5.4")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_API_KEY", "sk-vision-key")
    monkeypatch.setenv("SMARTACCESS_AI_VISION_TIMEOUT_SECONDS", "90")

    monkeypatch.setenv("SMARTACCESS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTACCESS_AUTOMATION_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_VISION_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_PLATFORM_PROVIDER", "stub")
    monkeypatch.setenv("SMARTACCESS_RABBITMQ_ENABLED", "false")

    from smartaccess.bootstrap.runtime import build_runtime_facade
    from smartaccess.shared.config.settings import AppSettings

    settings = AppSettings.from_env()
    facade = build_runtime_facade(settings)

    # WorkflowService 内部装的 draft_generator 应该是 text provider
    workflows_service = facade.providers()["workflows"]
    text_gen = workflows_service._draft_generator
    assert text_gen is not None
    assert text_gen._provider == "deepseek"
    assert text_gen._model == "deepseek-v4-pro"

    # facade 的 ai_generator 应该是 vision provider
    vision_gen = facade._ai_generator
    assert vision_gen is not None
    assert vision_gen._provider == "codex"
    assert vision_gen._model == "gpt-5.4"
```

- [ ] **Step 2: 运行测试**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py::test_build_runtime_facade_routes_text_and_vision_separately -v`

Expected: PASS。

- [ ] **Step 3: 运行整个测试文件做回归**

Run: `python -m pytest tests/integration/test_settings_ai_text_vision.py -v`

Expected: PASS（6 个测试用例全绿）。

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_settings_ai_text_vision.py
git commit -m "验证 build_runtime_facade 把 text/vision generator 装到正确位置"
```

---

## Task 7: 更新 `.env` 配置文件

**Files:**
- Modify: `E:\github_project\SmartAccess\.env`

**说明：** 把当前 .env 里现有的"deepseek 块（注释）+ codex 块（启用）"两组单组配置，改造成 TEXT（deepseek）+ VISION（codex）两组新写法。**保留** 旧单组写法作为注释示例，方便理解 fallback 行为。

- [ ] **Step 1: 替换 `.env` 里 AI 配置段落**

编辑 `E:\github_project\SmartAccess\.env`，找到第 11-23 行：

```dotenv
# 使用deepseek模型（无法识别图片）
#SMARTACCESS_AI_PROVIDER=deepseek
#SMARTACCESS_AI_BASE_URL=https://api.deepseek.com/v1
#SMARTACCESS_AI_MODEL=deepseek-v4-pro
#SMARTACCESS_AI_API_KEY=sk-5bbc4e66aec54557bf916ac693699e5f
#SMARTACCESS_AI_TIMEOUT_SECONDS=60

# 使用codex模型（可以识别图片）
SMARTACCESS_AI_PROVIDER=codex
SMARTACCESS_AI_BASE_URL=https://code.ppchat.vip/v1
SMARTACCESS_AI_MODEL=gpt-5.4
SMARTACCESS_AI_API_KEY=sk-Dq4j9qzR1QhN8NcyTyYWiskcie4YaVDFKywNfGkuZeq0NJ0K
SMARTACCESS_AI_TIMEOUT_SECONDS=60
```

整段替换为：

```dotenv
# === AI 模型配置（文字 LLM + 多模态 分离）===
SMARTACCESS_AI_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36

# 文字 LLM —— 用于 AI 生成工作流（不需要图片识别）
SMARTACCESS_AI_TEXT_PROVIDER=deepseek
SMARTACCESS_AI_TEXT_BASE_URL=https://api.deepseek.com/v1
SMARTACCESS_AI_TEXT_MODEL=deepseek-v4-pro
SMARTACCESS_AI_TEXT_API_KEY=sk-5bbc4e66aec54557bf916ac693699e5f
SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS=60

# 多模态 —— 用于 AI 辅助接入（需要识别截图）
SMARTACCESS_AI_VISION_PROVIDER=codex
SMARTACCESS_AI_VISION_BASE_URL=https://code.ppchat.vip/v1
SMARTACCESS_AI_VISION_MODEL=gpt-5.4
SMARTACCESS_AI_VISION_API_KEY=sk-Dq4j9qzR1QhN8NcyTyYWiskcie4YaVDFKywNfGkuZeq0NJ0K
SMARTACCESS_AI_VISION_TIMEOUT_SECONDS=60

# === 向后兼容（仅当 TEXT_* / VISION_* 都未配时生效）===
# 旧单组写法：TEXT 和 VISION 都使用同一组配置
# SMARTACCESS_AI_PROVIDER=codex
# SMARTACCESS_AI_BASE_URL=https://code.ppchat.vip/v1
# SMARTACCESS_AI_MODEL=gpt-5.4
# SMARTACCESS_AI_API_KEY=sk-Dq4j9qzR1QhN8NcyTyYWiskcie4YaVDFKywNfGkuZeq0NJ0K
# SMARTACCESS_AI_TIMEOUT_SECONDS=60
```

- [ ] **Step 2: 验证 `.env` 语法正确**

Run:
```bash
python -c "import sys; sys.path.insert(0, 'src'); from smartaccess.shared.config.settings import AppSettings; s = AppSettings.from_env(); print('text:', s.ai_text_provider, s.ai_text_model); print('vision:', s.ai_vision_provider, s.ai_vision_model)"
```

Expected: 输出 `text: deepseek deepseek-v4-pro` 和 `vision: codex gpt-5.4`。

注意：因为 `.env` 是项目本地的，**不提交 git**（`.gitignore` 通常排除）。仅本地修改，不执行 commit 步骤。

---

## Task 8: 更新 `.envexample` 示例

**Files:**
- Modify: `E:\github_project\SmartAccess\.envexample`

- [ ] **Step 1: 替换 `.envexample` 里 AI 配置段落**

编辑 `E:\github_project\SmartAccess\.envexample`，找到第 16-28 行：

```dotenv
# ---- AI 模型配置 ----
SMARTACCESS_AI_PROVIDER=template
SMARTACCESS_AI_BASE_URL=https://fufei.mossx.ai/v1
SMARTACCESS_AI_MODEL=GPT-5.4
SMARTACCESS_AI_API_KEY=
SMARTACCESS_AI_TIMEOUT_SECONDS=30
SMARTACCESS_AI_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36

# DeepSeek fallback (used when SMARTACCESS_AI_PROVIDER=deepseek).
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT_SECONDS=30
```

整段替换为：

```dotenv
# ---- AI 模型配置（文字 LLM + 多模态 分离）----
SMARTACCESS_AI_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36

# 文字 LLM —— 用于 AI 生成工作流（不需要图片识别）
# provider=template 时禁用；可选值：deepseek、codex 或其他 OpenAI 兼容供应商
SMARTACCESS_AI_TEXT_PROVIDER=template
SMARTACCESS_AI_TEXT_BASE_URL=https://fufei.mossx.ai/v1
SMARTACCESS_AI_TEXT_MODEL=GPT-5.4
SMARTACCESS_AI_TEXT_API_KEY=
SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS=30

# 多模态 —— 用于 AI 辅助接入（需要识别截图）
# provider=template 时禁用；目前仅 codex 走 Responses 接口支持图片
SMARTACCESS_AI_VISION_PROVIDER=template
SMARTACCESS_AI_VISION_BASE_URL=https://fufei.mossx.ai/v1
SMARTACCESS_AI_VISION_MODEL=GPT-5.4
SMARTACCESS_AI_VISION_API_KEY=
SMARTACCESS_AI_VISION_TIMEOUT_SECONDS=30

# 向后兼容（可选）：仅当 TEXT_* / VISION_* 都未配时生效，TEXT 和 VISION 共用此组
# SMARTACCESS_AI_PROVIDER=template
# SMARTACCESS_AI_BASE_URL=https://fufei.mossx.ai/v1
# SMARTACCESS_AI_MODEL=GPT-5.4
# SMARTACCESS_AI_API_KEY=
# SMARTACCESS_AI_TIMEOUT_SECONDS=30
```

- [ ] **Step 2: Commit**

```bash
git add .envexample
git commit -m "更新 .envexample 为 TEXT/VISION 分离配置示例"
```

---

## Task 9: 更新 `README.md` 的 AI 配置说明

**Files:**
- Modify: `E:\github_project\SmartAccess\README.md:190-198`（AI 环境变量段落）

- [ ] **Step 1: 替换 README.md 里 AI 配置段落**

编辑 `E:\github_project\SmartAccess\README.md`，找到第 194-198 行：

```markdown
- `SMARTACCESS_AI_PROFILES` / `SMARTACCESS_AI_ACTIVE_PROFILE`：OpenAI-compatible 多模型档案列表与默认档案。
- `SMARTACCESS_AI_PROFILE_{ID}_PROVIDER` / `SMARTACCESS_AI_PROFILE_{ID}_BASE_URL` / `SMARTACCESS_AI_PROFILE_{ID}_MODEL` / `SMARTACCESS_AI_PROFILE_{ID}_API_KEY`：单个模型档案配置。
- `SMARTACCESS_AI_PROFILE_{ID}_TIMEOUT_SECONDS`：单个模型档案的请求超时，单位秒。
- `SMARTACCESS_AI_PROFILE_{ID}_WIRE_API`：模型网关接口类型，Codex/Responses 网关使用 `responses`，DeepSeek 等 Chat Completions 兼容网关使用 `chat_completions`。
- `SMARTACCESS_AI_USER_AGENT`：AI 请求头中的 `User-Agent`，用于兼容部分网关或 Cloudflare 策略。
```

整段替换为：

```markdown
- `SMARTACCESS_AI_TEXT_PROVIDER` / `SMARTACCESS_AI_TEXT_BASE_URL` / `SMARTACCESS_AI_TEXT_MODEL` / `SMARTACCESS_AI_TEXT_API_KEY` / `SMARTACCESS_AI_TEXT_TIMEOUT_SECONDS`：文字 LLM 配置，用于 **AI 生成工作流**（不需要图片识别）。
- `SMARTACCESS_AI_VISION_PROVIDER` / `SMARTACCESS_AI_VISION_BASE_URL` / `SMARTACCESS_AI_VISION_MODEL` / `SMARTACCESS_AI_VISION_API_KEY` / `SMARTACCESS_AI_VISION_TIMEOUT_SECONDS`：多模态模型配置，用于 **AI 辅助接入**（需要识别截图）。目前仅 `provider=codex` 通过 Responses 接口支持图片，其他 provider 走 Chat Completions 仅文字。
- `SMARTACCESS_AI_USER_AGENT`：AI 请求头中的 `User-Agent`，用于兼容部分网关或 Cloudflare 策略；TEXT 与 VISION 共享。
- 向后兼容：若未配上述 TEXT/VISION 变量，但配了旧的 `SMARTACCESS_AI_PROVIDER` / `SMARTACCESS_AI_BASE_URL` / `SMARTACCESS_AI_MODEL` / `SMARTACCESS_AI_API_KEY` / `SMARTACCESS_AI_TIMEOUT_SECONDS` 单组写法，TEXT 与 VISION 都回退到此组；进一步若旧单组也未配，再回退到早期 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `DEEPSEEK_TIMEOUT_SECONDS`。
- `provider=template` 时对应用途的 AI 功能禁用（不发起外部请求）。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "README 更新 AI 文字模型与多模态模型分离配置说明"
```

---

## Task 10: 端到端冒烟验证

**Files:** 无（仅运行验证）

**说明：** 按 spec 的"集成验证"策略，启动应用做两次实际 AI 调用，观察日志确认 text/vision 各自走了对应 provider。

- [ ] **Step 1: 启动桌面应用**

按项目惯例启动命令（参考项目 README 或现有启动脚本）。如果项目有 `python -m smartaccess.desktop` 或类似入口，运行它。

Expected: 应用正常启动，日志中不出现 AI 装配错误。

- [ ] **Step 2: 触发 AI 生成工作流**

在 UI 里触发 AI 生成工作流功能（输入提示词，点生成）。观察后台日志。

Expected: 日志出现 `provider=deepseek` 或工作流服务记录的 deepseek 模型调用，**不**出现 codex。

- [ ] **Step 3: 触发 AI 辅助接入**

在 UI 里触发 AI 辅助接入设备功能（上传截图，输入描述，点生成）。观察后台日志。

Expected: 日志出现 `provider=codex` 或设备接入服务记录的 codex 模型调用，**不**出现 deepseek。

- [ ] **Step 4: 如果验证失败**

如果两个 AI 功能走了错误的 provider，检查：
- `.env` 文件是否正确配置了 TEXT_* / VISION_* 两组（Task 7）
- `bootstrap/runtime.py` 的装配语句是否正确（Task 5 的 Step 2）
- 通过 `python -c "..."` 直接打印 `AppSettings.from_env()` 的字段值，确认配置读取无误

修复后回到 Step 1 重试。

- [ ] **Step 5: 总结**

无代码改动，无需 commit。在交付时告知用户：
- 哪些文件被修改了
- 哪些任务完成了
- 冒烟验证的结果
