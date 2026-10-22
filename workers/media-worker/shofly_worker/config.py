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
    max_bytes: int = 50 * 1024 * 1024            # legacy default download ceiling and hosted Bot API upload cap
    download_max_bytes: int = 8 * 1024 * 1024 * 1024  # source download cap, independent of per-part upload cap
    download_timeout: int = 1800
    heartbeat_seconds: int = 60
    poll_seconds: int = 30                       # pause between queue checks when idle (CLI loop)
    tmp_dir: str = "/tmp/shofly"
    allowed_hosts: str = ""                      # optional extra allowlist (comma separated)
    downloader: str = "httpx"                    # httpx (default) | aria2c (allowlisted hosts only)
    httpx_parallel_connections: int = 8
    httpx_chunk_size_mb: int = 8
    aria2_connections: int = 4                 # 1-8 parallel connections per trusted source
    aria2_retries: int = 3                     # 1-5 attempts per transfer
    ffmpeg_verify: bool = False               # opt-in full decode before upload
    ffmpeg_verify_timeout: int = 600           # seconds; capped at 3600
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str = "/content/drive/MyDrive/Shofly/telegram_bot"
    mtproto_max_bytes: int = 2 * 1024 * 1024 * 1024
    mtproto_parallel_workers: int = 16  # total upload tasks: 4 per connection
    mtproto_connections: int = 4  # independent MTProto clients
    generate_qualities: bool = False  # opt-in; FFmpeg CPU, disk and Telegram uploads are costly
    transcode_timeout: int = 7200
    split_large_media: bool = False
    segment_max_bytes: int = 0  # 0 means provider's own max size
    persistent_download_dir: str = ""  # optional mounted storage for partial transfers
