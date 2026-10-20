import shutil
import uuid
from pathlib import Path
from typing import Protocol
import httpx
from shofly_worker.errors import WorkerError


class MediaProvider(Protocol):
    name: str
    def upload(self, local_path: Path, meta: dict) -> str: ...
    def verify(self, ref: str, size: int) -> bool: ...
    def delete(self, ref: str) -> None: ...


class LocalDirProvider:
    """Dev/test provider: copies into a folder. Not for production delivery."""
    name = "local"

    def __init__(self, root: str):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, meta: dict) -> str:
        ref = f"{uuid.uuid4().hex}{local_path.suffix}"
        shutil.copyfile(local_path, self.root / ref)
        return ref

    def verify(self, ref: str, size: int) -> bool:
        f = self.root / ref
        return f.is_file() and f.stat().st_size == size

    def delete(self, ref: str) -> None:
        (self.root / ref).unlink(missing_ok=True)


class TelegramProvider:
    """Stores files in a private channel via the Bot API (sendDocument). NOT tested against live Telegram.
    Hosted Bot API caps uploads at 50 MB; a file id is not a browser-playable URL (bot delivery only).
    Verification compares the size Telegram reports in its upload receipt; getFile re-check works only up to 20 MB."""
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, max_bytes: int = 50 * 1024 * 1024, http: httpx.Client | None = None):
        self.base, self.chat, self.max = f"https://api.telegram.org/bot{bot_token}", chat_id, max_bytes
        self.http, self._receipts = http or httpx.Client(timeout=600.0), {}

    def upload(self, local_path: Path, meta: dict) -> str:
        if local_path.stat().st_size > self.max:
            raise WorkerError("FILE_TOO_LARGE", "File exceeds the Telegram upload limit.", False)
        try:
            with open(local_path, "rb") as f:
                r = self.http.post(f"{self.base}/sendDocument", data={"chat_id": self.chat, "disable_notification": "true"},
                                   files={"document": (local_path.name, f)})
            body = r.json()
        except (httpx.HTTPError, ValueError):
            raise WorkerError("UPLOAD_FAILED", "Upload to storage failed.", True)
        if not body.get("ok"):
            raise WorkerError("UPLOAD_FAILED", "Storage rejected the upload.", r.status_code >= 500 or r.status_code == 429)
        m = body["result"]; d = m["document"]
        ref = f"{m['chat']['id']}:{m['message_id']}:{d['file_id']}"
        self._receipts[ref] = d.get("file_size")
        return ref

    def verify(self, ref: str, size: int) -> bool:
        if self._receipts.get(ref) != size:
            return False
        if size <= 20 * 1024 * 1024:  # getFile only works for small files
            try:
                r = self.http.get(f"{self.base}/getFile", params={"file_id": ref.split(":", 2)[2]}).json()
                return bool(r.get("ok")) and r["result"].get("file_size") == size
            except (httpx.HTTPError, ValueError):
                return False
        return True

    def delete(self, ref: str) -> None:
        chat, mid, _ = ref.split(":", 2)
        try:
            self.http.post(f"{self.base}/deleteMessage", data={"chat_id": chat, "message_id": mid})
        except httpx.HTTPError:
            pass
