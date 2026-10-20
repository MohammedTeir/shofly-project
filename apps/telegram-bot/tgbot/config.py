from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: str
    bot_api_token: str
    api_base_url: str = "http://localhost:8000"
    public_app_url: str | None = None
    throttle_max: int = 20
    throttle_window: int = 30
