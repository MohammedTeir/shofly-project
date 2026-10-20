import time
from dataclasses import dataclass


@dataclass
class Session:
    token: str
    lang: str


class SessionCache:
    """Short-lived per-Telegram-user API sessions (backend tokens last 15 min; we refresh at 10)."""
    def __init__(self, ttl: int = 600):
        self.ttl, self._d = ttl, {}

    def get(self, tg_id: int) -> Session | None:
        v = self._d.get(tg_id)
        return v[0] if v and v[1] > time.monotonic() else None

    def put(self, tg_id: int, s: Session):
        self._d[tg_id] = (s, time.monotonic() + self.ttl)
