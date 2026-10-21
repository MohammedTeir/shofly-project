import uuid
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    api_base_url: str
    worker_api_token: str
    worker_id: str = f"colab-{uuid.uuid4().hex[:8]}"
    provider: str = "local"                      # local | telegram
    local_dir: str = "./stored"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None          # private storage channel id
    max_bytes: int = 50 * 1024 * 1024            # Bot API upload cap; raise only with a local Bot API server
    download_timeout: int = 1800
    heartbeat_seconds: int = 60
    poll_seconds: int = 30                       # pause between queue checks when idle (CLI loop)
    tmp_dir: str = "/tmp/shofly"
    allowed_hosts: str = ""                      # optional extra allowlist (comma separated)
    downloader: str = "httpx"                    # httpx (default) | aria2c (allowlisted hosts only)
    aria2_connections: int = 4                 # 1-8 parallel connections per trusted source
    aria2_retries: int = 3                     # 1-5 attempts per transfer
    persistent_download_dir: str = ""  # optional mounted storage for partial transfers
