"""Application configuration via pydantic-settings.

Env vars are flat (e.g. REDIS_HOST, GITHUB_TOKEN) and loaded from `.env`.
Grouped accessors (settings.github, settings.llm, ...) expose them as cohesive
views matching the spec's logical groups.
"""

from __future__ import annotations

from functools import cached_property, lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Group:
    """Lightweight attribute bag for a settings group."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"{type(self).__name__}({self.__dict__!r})"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- app ----
    app_env: str = "development"
    app_version: str = "0.1.0"
    app_name: str = "cap-pr-review"
    log_level: str = "INFO"
    log_json: bool = False

    # ---- api ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    rate_limit_per_minute: int = 60

    # ---- llm / anthropic ----
    primary_model: str = "deepseek-v4-pro"
    fallback_model: str = "deepseek-v4-pro"
    llm_base_url: str | None = None
    model_provider: str = "deepseek"  # "anthropic" | "deepseek"
    llm_api_key: str | None = None
    llm_max_tokens: int = 4096
    llm_requests_per_second: float = 200.0
    llm_timeout_seconds: float = 120.0
    ssl_cert_file: str | None = None

    # ---- github ----
    github_token: str | None = None
    github_api_base_url: str = "https://api.github.com"
    github_webhook_secret: str | None = None
    github_ca_bundle: str | None = None

    # ---- redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- chromadb ----
    chromadb_mode: str = "embedded"  # "embedded" | "http"
    chromadb_host: str = "localhost"
    chromadb_port: int = 8001
    chromadb_persist_dir: str = ".chroma"
    chromadb_collection: str = "owasp_knowledge"

    # ---- langfuse ----
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    # ---- worker ----
    worker_max_jobs: int = 5
    worker_job_timeout: int = 600

    # ---- derived / helpers ----
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @cached_property
    def app(self) -> _Group:
        return _Group(
            env=self.app_env,
            version=self.app_version,
            name=self.app_name,
            log_level=self.log_level,
            log_json=self.log_json,
        )

    @cached_property
    def api(self) -> _Group:
        return _Group(
            host=self.api_host,
            port=self.api_port,
            prefix=self.api_prefix,
            cors_origins=self.cors_origins,
            rate_limit_per_minute=self.rate_limit_per_minute,
        )

    @cached_property
    def llm(self) -> _Group:
        return _Group(
            primary_model=self.primary_model,
            fallback_model=self.fallback_model,
            base_url=self.llm_base_url or None,
            provider=self.model_provider,
            api_key=self.llm_api_key,
            max_tokens=self.llm_max_tokens,
            requests_per_second=self.llm_requests_per_second,
            timeout=self.llm_timeout_seconds,
            ssl_cert_file=self.ssl_cert_file or None,
        )

    @cached_property
    def github(self) -> _Group:
        return _Group(
            token=self.github_token,
            base_url=self.github_api_base_url.rstrip("/"),
            webhook_secret=self.github_webhook_secret,
            ca_bundle=self.github_ca_bundle or None,
        )

    @cached_property
    def redis(self) -> _Group:
        return _Group(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            dsn=self.redis_dsn,
        )

    @cached_property
    def chromadb(self) -> _Group:
        return _Group(
            mode=self.chromadb_mode,
            host=self.chromadb_host,
            port=self.chromadb_port,
            persist_dir=self.chromadb_persist_dir,
            collection=self.chromadb_collection,
        )

    @cached_property
    def langfuse(self) -> _Group:
        return _Group(
            enabled=self.langfuse_enabled,
            public_key=self.langfuse_public_key,
            secret_key=self.langfuse_secret_key,
            host=self.langfuse_host,
        )

    @cached_property
    def worker(self) -> _Group:
        return _Group(
            max_jobs=self.worker_max_jobs,
            job_timeout=self.worker_job_timeout,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
