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


class MTProtoTelegramProvider:
    """Telegram bot MTProto upload through Telethon. Uses a private storage channel.

    Uses the same provider reference format as TelegramProvider, preserving
    backend compatibility. Upload limit defaults to 2 GiB, subject to Telegram limits.
    """
    name = "telegram"

    def __init__(self, api_id: int, api_hash: str, bot_token: str, chat_id: str,
                 session_path: str, max_bytes: int = 2 * 1024**3):
        if not api_id or not api_hash or not bot_token or not chat_id:
            raise ValueError("MTProto API credentials and storage channel are required")
        self.api_id, self.api_hash, self.bot_token = api_id, api_hash, bot_token
        self.chat_id, self.session_path, self.max = int(chat_id), session_path, max_bytes
        self._receipts = {}

    def _run(self, operation):
        import asyncio
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from pathlib import Path
        async def execute():
            Path(self.session_path).parent.mkdir(parents=True, exist_ok=True)
            async with TelegramClient(self.session_path, self.api_id, self.api_hash) as client:
                if not await client.is_user_authorized():
                    await client.start(bot_token=self.bot_token)
                return await operation(client)
        return asyncio.run(execute())

    def upload(self, local_path: Path, meta: dict) -> str:
        size = local_path.stat().st_size
        if size > self.max:
            raise WorkerError("FILE_TOO_LARGE", "File exceeds configured MTProto upload limit.", False)
        async def send(client):
            message = await client.send_file(self.chat_id, str(local_path), force_document=True)
            if not message or not message.file:
                raise RuntimeError("Telegram did not return a file receipt")
            return message.id, message.file.size, message.document.id
        try:
            mid, reported_size, document_id = self._run(send)
        except Exception:
            raise WorkerError("UPLOAD_FAILED", "MTProto upload failed.", True)
        ref = f"{self.chat_id}:{mid}:mtproto-{document_id}"
        self._receipts[ref] = reported_size
        return ref

    def verify(self, ref: str, size: int) -> bool:
        if self._receipts.get(ref) != size:
            return False
        try:
            mid = int(ref.split(":", 2)[1])
            async def get(client):
                message = await client.get_messages(self.chat_id, ids=mid)
                return bool(message and message.file and message.file.size == size)
            return self._run(get)
        except Exception:
            return False

    def delete(self, ref: str) -> None:
        try:
            mid = int(ref.split(":", 2)[1])
            async def remove(client):
                await client.delete_messages(self.chat_id, [mid])
            self._run(remove)
        except Exception:
            pass
