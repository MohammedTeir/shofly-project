import httpx


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(f"{status} {code}")
        self.status, self.code = status, code


class BotApi:
    """Thin client for the backend. All authorization decisions stay server-side."""

    def __init__(self, base_url: str, bot_token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._bot_token = bot_token
        self._c = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=10.0)

    async def close(self):
        await self._c.aclose()

    async def _req(self, method: str, path: str, token: str | None = None, headers: dict | None = None, **kw):
        h = dict(headers or {})
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = await self._c.request(method, "/api/v1" + path, headers=h, **kw)
        if r.status_code >= 400:
            try:
                code = r.json()["error"]["code"]
            except Exception:
                code = "HTTP_ERROR"
            raise ApiError(r.status_code, code)
        return r.json()

    async def auth(self, tg_user: dict) -> dict:
        return await self._req("POST", "/bot/auth", headers={"X-Bot-Token": self._bot_token}, json=tg_user)

    async def set_language(self, token: str, lang: str) -> dict:
        return await self._req("PATCH", "/me/preferences", token, json={"preferred_language": lang})

    async def list_titles(self, token: str, kind: str, offset: int, limit: int) -> dict:
        return await self._req("GET", f"/catalog/{'movies' if kind == 'movie' else 'series'}", token,
                               params={"cursor": offset, "limit": limit})

    async def search(self, token: str, q: str, limit: int = 8) -> dict:
        return await self._req("GET", "/catalog/search", token, params={"q": q, "limit": limit})

    async def title(self, token: str, kind: str, item_id: str) -> dict:
        return await self._req("GET", f"/{'movies' if kind == 'movie' else 'series'}/{item_id}", token)

    async def season(self, token: str, series_id: str, number: int) -> dict:
        return await self._req("GET", f"/catalog/series/{series_id}/seasons/{number}", token)

    async def episode_qualities(self, token: str, episode_id: str) -> dict:
        return await self._req("GET", f"/catalog/episodes/{episode_id}/qualities", token)

    async def favorites(self, token: str, offset: int, limit: int) -> dict:
        return await self._req("GET", "/me/favorites", token, params={"cursor": offset, "limit": limit})

    async def set_favorite(self, token: str, kind: str, item_id: str, on: bool) -> dict:
        return await self._req("PUT" if on else "DELETE", f"/me/favorites/{kind}/{item_id}", token)

    async def telegram_delivery(self, token: str, asset_id: str) -> dict:
        """Needs both the user's token and the shared bot secret; the backend re-checks rights/territory/entitlement."""
        return await self._req("POST", f"/media/{asset_id}/telegram-delivery", token, headers={"X-Bot-Token": self._bot_token})
