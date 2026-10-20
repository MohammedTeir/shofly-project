import logging
import time
from collections import defaultdict, deque
import httpx
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from tgbot.api import ApiError, BotApi
from tgbot.localization import t
from tgbot.session import Session, SessionCache
from tgbot.screens import show

log = logging.getLogger("tgbot")


class AuthMiddleware(BaseMiddleware):
    """Identity comes from the verified Telegram update sender (AUTH-03), never from message text."""
    def __init__(self, api: BotApi, cache: SessionCache | None = None):
        self.api, self.cache = api, cache or SessionCache()

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u is None or u.is_bot:
            return None
        s = self.cache.get(u.id)
        try:
            if s is None:
                res = await self.api.auth({"id": u.id, "username": u.username, "first_name": u.first_name,
                                           "last_name": u.last_name, "language_code": u.language_code})
                s = Session(res["access_token"], res["user"]["preferred_language"])
                self.cache.put(u.id, s)
            data["session"] = s
            return await handler(event, data)
        except ApiError as e:
            log.warning("api error %s", e)
            key = "not_found" if e.code == "NOT_FOUND" else "error"
            await show(event, t(s.lang if s else None, key))
        except httpx.HTTPError:
            log.exception("backend unreachable")
            await show(event, t(s.lang if s else None, "error"))


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict[int, deque] = defaultdict(deque)
        self.warned: set[int] = set()

    async def __call__(self, handler, event, data):
        uid, now = data["event_from_user"].id, time.monotonic()
        q = self.hits[uid]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            if uid not in self.warned:  # warn once per burst, then drop silently
                self.warned.add(uid)
                await show(event, t(data["session"].lang, "throttled"))
            return None
        self.warned.discard(uid)
        q.append(now)
        return await handler(event, data)
