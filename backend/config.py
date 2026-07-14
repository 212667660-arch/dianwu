from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("A3_DATA_DIR", BASE_DIR)).expanduser().resolve()
ENV_FILE = DATA_DIR / ".env"
SUPPORTED_MODEL_PROVIDERS = {"openai", "anthropic"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_provider: str = "openai"
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    anthropic_version: str = "2023-06-01"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com"
    openai_model: str = "deepseek-v4-pro"
    hy_api_key: str = ""
    hy_base_url: str = ""
    hy_model: str = ""

    app_env: str = "development"
    database_url: str = ""
    cors_origins: str = "http://localhost:5173"
    request_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    resource_cache_ttl_seconds: int = Field(default=86400, ge=0, le=604800)
    web_search_enabled: bool = True
    web_search_timeout_seconds: float = Field(default=8.0, ge=2.0, le=30.0)
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    web_search_providers: str = "sogou,duckduckgo,bing"
    desktop_token: str = ""
    allow_local_model_gateway: bool = False
    api_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    web_search_rate_limit_per_minute: int = Field(default=30, ge=1, le=300)
    diagnosis_history_message_limit: int = Field(default=12, ge=2, le=64)
    diagnosis_history_max_characters: int = Field(default=48000, ge=8000, le=200000)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

    @property
    def resolved_provider(self) -> str:
        return self.model_provider.strip().lower()

    @property
    def resolved_api_key(self) -> str:
        return (self.model_api_key or self.openai_api_key or self.hy_api_key).strip()

    @property
    def resolved_base_url(self) -> str:
        return (self.model_base_url or self.openai_base_url or self.hy_base_url).strip()

    @property
    def resolved_model_name(self) -> str:
        return (self.model_name or self.openai_model or self.hy_model).strip()

    @property
    def is_model_configured(self) -> bool:
        key = self.resolved_api_key
        return (
            self.resolved_provider in SUPPORTED_MODEL_PROVIDERS
            and bool(self.resolved_base_url)
            and bool(self.resolved_model_name)
            and bool(key)
            and not key.startswith("sk-请替换")
            and key != "YOUR_API_KEY"
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
