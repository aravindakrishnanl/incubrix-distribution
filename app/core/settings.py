"""Application settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="before")
    @classmethod
    def map_env_aliases(cls, data: Any) -> Any:
        """Map alternative environment variable spellings to expected settings fields."""
        if isinstance(data, dict):
            # DEV_API_KEY / DEV_API_BASE_URL -> devto_api_key / devto_api_base_url
            if not data.get("devto_api_key") and data.get("dev_api_key"):
                data["devto_api_key"] = data["dev_api_key"]
            if not data.get("devto_api_base_url") and data.get("dev_api_base_url"):
                data["devto_api_base_url"] = data["dev_api_base_url"]
            # GHOST_API_KEY -> ghost_admin_api_key
            if not data.get("ghost_admin_api_key") and data.get("ghost_api_key"):
                data["ghost_admin_api_key"] = data["ghost_api_key"]
        return data

    # ── Application ─────────────────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"
    api_bearer_token: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist"
    database_url_sync: str = "postgresql+psycopg2://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist"
    test_database_url: str = "postgresql+asyncpg://incubrix:incubrix_dev_password@localhost:5432/incubrix_dist_test"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    @field_validator("test_database_url", mode="after")
    @classmethod
    def test_db_must_be_separate(cls, v: str) -> str:
        """Safety guard: test database URL must contain '_test' to prevent
        accidentally wiping a production or development database."""
        if "_test" not in v:
            raise ValueError(
                "TEST_DATABASE_URL must contain '_test' to prevent accidental data loss. "
                f"Got: {v!r}"
            )
        return v

    # ── Storage ──────────────────────────────────────────────────────────────
    storage_backend: str = "s3"  # 's3' | 'local'
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin_dev_secret"
    s3_bucket: str = "incubrix-dist"
    s3_region: str = "us-east-1"
    local_storage_path: str = "./data/local_storage"

    # ── Security ──────────────────────────────────────────────────────────────
    credential_encryption_key: str = ""
    hmac_signing_secret: str = ""

    # ── HTTP ─────────────────────────────────────────────────────────────────
    http_timeout_seconds: int = 30
    http_max_retries: int = 3

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # ── Simulation mode ───────────────────────────────────────────────────────
    simulation_mode: bool = True

    # ── Connector toggles ─────────────────────────────────────────────────────
    connector_discourse_enabled: bool = True
    connector_lemmy_enabled: bool = True
    connector_devto_enabled: bool = True
    connector_ghost_enabled: bool = True
    connector_webhook_hmac_enabled: bool = True
    connector_assisted_enabled: bool = True

    # ── Per-connector credentials (runtime use only — never logged) ───────────
    discourse_base_url: str = "http://localhost:4000"
    discourse_api_key: str = ""
    discourse_api_username: str = "system"

    lemmy_base_url: str = "http://localhost:8536"
    lemmy_username: str = "admin"
    lemmy_password: str = ""
    lemmy_community_id: int = 2

    devto_api_key: str = ""
    devto_api_base_url: str = "https://dev.to/api"

    ghost_admin_api_key: str = ""
    ghost_content_api_key: str = ""
    ghost_api_base_url: str = "http://localhost:2368"

    def connector_enabled(self, connector_key: str) -> bool:
        """Check whether a connector is enabled by its key."""
        mapping = {
            "discourse": self.connector_discourse_enabled,
            "lemmy": self.connector_lemmy_enabled,
            "devto": self.connector_devto_enabled,
            "ghost": self.connector_ghost_enabled,
            "webhook_hmac": self.connector_webhook_hmac_enabled,
            "assisted": self.connector_assisted_enabled,
        }
        return mapping.get(connector_key, False)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
