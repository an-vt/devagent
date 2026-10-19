"""Environment-backed application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_APP_PORT = "8080"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass
class Config:
    """Configuration required to run devagent."""

    is_dev: bool = False
    app_port: str = DEFAULT_APP_PORT
    model: str = "deepseek-v4-flash"
    api_key: str = ""
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    log_level: str = DEFAULT_LOG_LEVEL
    max_context_tokens: int = 128_000

    @classmethod
    def from_env(cls) -> "Config":
        """Read configuration from the process environment and local .env."""
        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / ".env", override=False)

        app_port = os.getenv("APP_PORT", DEFAULT_APP_PORT)
        is_dev = os.getenv("ENVIRONMENT") == "development"
        log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)

        return cls(
            is_dev=is_dev,
            app_port=app_port,
            model=os.getenv("MODEL", "deepseek-v4-flash"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
            temperature=float(os.getenv("TEMPERATURE", "0")),
            log_level=log_level,
            max_context_tokens=int(os.getenv("MAX_CONTEXT_TOKENS", 128_000)),
        )
