"""应用配置读取。"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_AI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class AppSettings(BaseModel):
    """SmartAccess 运行配置。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    workspace_dir: Path = Field(default=Path("workspace"))
    log_level: str = Field(default="INFO")
    automation_provider: str = Field(default="stub")
    vision_provider: str = Field(default="stub")
    vision_api_url: str = Field(default="http://100.84.59.58:8090")
    platform_provider: str = Field(default="stub")
    ai_provider: str = Field(default="template")
    ai_api_key: str | None = Field(default=None)
    ai_base_url: str = Field(default="https://fufei.mossx.ai/v1")
    ai_model: str = Field(default="GPT-5.4")
    ai_timeout_seconds: float = Field(default=30.0, gt=0)
    ai_user_agent: str = Field(default=DEFAULT_AI_USER_AGENT)
    deepseek_api_key: str | None = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0)
    speclabos_base_url: str | None = Field(default=None)
    speclabos_api_key: str | None = Field(default=None)
    speclabos_timeout_seconds: float = Field(default=20.0, gt=0)
    edge_api_host: str = Field(default="127.0.0.1")
    edge_api_port: int = Field(default=7000, ge=1, le=65535)
    udp_host: str = Field(default="127.0.0.1")
    udp_port: int = Field(default=8889, ge=1, le=65535)
    udp_timeout_seconds: float = Field(default=6.0, gt=0)
    process_executor_provider: str = Field(default="stub")
    device_id: str = Field(default="")
    rabbitmq_host: str = Field(default="127.0.0.1")
    rabbitmq_port: int = Field(default=5672, ge=1, le=65535)
    rabbitmq_username: str = Field(default="guest")
    rabbitmq_password: str = Field(default="guest")
    rabbitmq_enabled: bool = Field(default=False)

    @classmethod
    def from_env(cls) -> "AppSettings":
        """从环境变量和项目根目录 .env 文件读取配置。

        Returns:
            应用配置对象。
        """

        env_file_values = cls._read_env_file()

        def _get(name: str, default: str | None = None) -> str | None:
            value = os.getenv(name)
            if value in (None, ""):
                value = env_file_values.get(name)
            return value if value not in (None, "") else default

        workspace_dir = _get("SMARTACCESS_WORKSPACE_DIR", "workspace")
        ai_base_url = _get(
            "SMARTACCESS_AI_BASE_URL",
            _get("DEEPSEEK_BASE_URL", "https://fufei.mossx.ai/v1"),
        )
        ai_model = _get(
            "SMARTACCESS_AI_MODEL",
            _get("DEEPSEEK_MODEL", "GPT-5.4"),
        )
        ai_timeout = _get(
            "SMARTACCESS_AI_TIMEOUT_SECONDS",
            _get("DEEPSEEK_TIMEOUT_SECONDS", "30"),
        )

        return cls(
            workspace_dir=Path(workspace_dir or "workspace"),
            log_level=_get("SMARTACCESS_LOG_LEVEL", "INFO") or "INFO",
            automation_provider=(
                _get("SMARTACCESS_AUTOMATION_PROVIDER", "stub") or "stub"
            ),
            vision_provider=_get("SMARTACCESS_VISION_PROVIDER", "stub") or "stub",
            vision_api_url=_get(
                "SMARTACCESS_VISION_API_URL", "http://100.84.59.58:8090"
            )
            or "http://100.84.59.58:8090",
            platform_provider=_get("SMARTACCESS_PLATFORM_PROVIDER", "stub") or "stub",
            ai_provider=_get("SMARTACCESS_AI_PROVIDER", "template") or "template",
            ai_api_key=_get("SMARTACCESS_AI_API_KEY", _get("DEEPSEEK_API_KEY")),
            ai_base_url=ai_base_url or "https://fufei.mossx.ai/v1",
            ai_model=ai_model or "GPT-5.4",
            ai_timeout_seconds=float(ai_timeout or "30"),
            ai_user_agent=(
                _get("SMARTACCESS_AI_USER_AGENT", DEFAULT_AI_USER_AGENT)
                or DEFAULT_AI_USER_AGENT
            ),
            deepseek_api_key=_get("DEEPSEEK_API_KEY"),
            deepseek_base_url=(
                _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                or "https://api.deepseek.com"
            ),
            deepseek_model=_get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat",
            deepseek_timeout_seconds=float(
                _get("DEEPSEEK_TIMEOUT_SECONDS", "30") or "30"
            ),
            speclabos_base_url=_get("SPECLABOS_BASE_URL"),
            speclabos_api_key=_get("SPECLABOS_API_KEY"),
            speclabos_timeout_seconds=float(
                _get("SPECLABOS_TIMEOUT_SECONDS", "20") or "20"
            ),
            edge_api_host=(
                _get("SMARTACCESS_EDGE_API_HOST", "127.0.0.1") or "127.0.0.1"
            ),
            edge_api_port=int(_get("SMARTACCESS_EDGE_API_PORT", "7000") or "7000"),
            udp_host=_get("SMARTACCESS_UDP_HOST", "127.0.0.1") or "127.0.0.1",
            udp_port=int(_get("SMARTACCESS_UDP_PORT", "8889") or "8889"),
            udp_timeout_seconds=float(
                _get("SMARTACCESS_UDP_TIMEOUT_SECONDS", "6") or "6"
            ),
            process_executor_provider=(
                _get("SMARTACCESS_PROCESS_EXECUTOR_PROVIDER", "stub") or "stub"
            ),
            device_id=_get("SMARTACCESS_DEVICE_ID", "") or "",
            rabbitmq_host=(
                _get("SMARTACCESS_RABBITMQ_HOST", "127.0.0.1") or "127.0.0.1"
            ),
            rabbitmq_port=int(_get("SMARTACCESS_RABBITMQ_PORT", "5672") or "5672"),
            rabbitmq_username=(
                _get("SMARTACCESS_RABBITMQ_USERNAME", "guest") or "guest"
            ),
            rabbitmq_password=(
                _get("SMARTACCESS_RABBITMQ_PASSWORD", "guest") or "guest"
            ),
            rabbitmq_enabled=(
                _get("SMARTACCESS_RABBITMQ_ENABLED", "false") or "false"
            ).lower()
            == "true",
        )

    @staticmethod
    def _read_env_file(path: Path | None = None) -> dict[str, str]:
        """读取 .env 文件内容。

        Args:
            path: 可选 .env 文件路径；为空时使用当前工作目录下的 .env。

        Returns:
            环境变量键值映射。
        """

        env_path = path or Path.cwd() / ".env"
        if not env_path.exists():
            return {}
        values: dict[str, str] = {}
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                values[key] = AppSettings._clean_env_value(value)
        return values

    @staticmethod
    def _clean_env_value(value: str) -> str:
        """清理 .env 中的引号包裹值。

        Args:
            value: 原始配置值。

        Returns:
            清理后的配置值。
        """

        cleaned = value.strip()
        if (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {"'", '"'}
        ):
            return cleaned[1:-1]
        return cleaned

    @property
    def ai_configured(self) -> bool:
        """在线 AI 配置是否可用。"""

        return bool(self.ai_api_key)

    @property
    def deepseek_configured(self) -> bool:
        """旧 DeepSeek 配置是否可用。"""

        return bool(self.deepseek_api_key)

    @property
    def speclabos_configured(self) -> bool:
        """SpecLabOS 平台配置是否可用。"""

        return bool(self.speclabos_base_url)

