from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./dev.db"
    telegram_bot_token: str
    jwt_signing_key: str
    access_token_ttl_seconds: int = 900
    initdata_max_age_seconds: int = 86400
    cors_origins: str = ""
    worker_api_token: str | None = None
    encryption_key: str | None = None
    import_allowed_hosts: str = ""
    job_lease_seconds: int = 300
    job_max_attempts: int = 3
    retry_backoff_seconds: int = 60
    bot_username: str | None = None
    billing_enabled: bool = False
    bootstrap_super_admin_telegram_ids: str = ""
    bot_api_token: str | None = None
    streaming_gateway_url: str | None = None
    streaming_signing_key: str | None = None
    streaming_internal_secret: str | None = None
    default_language: str = "ar"
    supported_languages: str = "ar,en"

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def import_hosts(self) -> set[str]:
        return {x.strip().lower() for x in self.import_allowed_hosts.split(",") if x.strip()}

    @property
    def bootstrap_admin_ids(self) -> list[int]:
        out = []
        for x in self.bootstrap_super_admin_telegram_ids.split(","):
            x = x.strip()
            if x.lstrip("-").isdigit():
                out.append(int(x))
        return out

    @property
    def languages(self) -> list[str]:
        return [x.strip() for x in self.supported_languages.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
