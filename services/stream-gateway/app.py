"""Shofly Telegram-backed streaming gateway. Deploy separately from the API."""
import os
import re
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from telethon import TelegramClient

API = os.environ["SHOFLY_API_URL"].rstrip("/")
SECRET = os.environ["STREAMING_INTERNAL_SECRET"]
ORIGIN = os.environ["MINI_APP_ORIGIN"].rstrip("/")
MAX_RANGE = 8 * 1024 * 1024
RANGE = re.compile(r"^bytes=(\d+)-(\d*)$")
client = TelegramClient(os.environ.get("TELEGRAM_SESSION", "/data/shofly_stream"),
                        int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
http = httpx.AsyncClient(timeout=15.0, follow_redirects=False)


@asynccontextmanager
async def lifespan(app):
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(bot_token=os.environ["TELEGRAM_BOT_TOKEN"])
    me = await client.get_me()
    if not me or not me.bot:
        raise RuntimeError("Streaming MTProto session must be a bot")
    yield
    await client.disconnect()
    await http.aclose()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/health/live")
async def health():
    return {"status": "ok"}


@app.get("/stream/{asset_id}")
async def stream(asset_id: UUID, request: Request, ticket: str = ""):
    # No CORS wildcard. Query tickets are short-lived and must not appear in access logs.
    if request.headers.get("origin") not in (None, ORIGIN):
        raise HTTPException(403)
    if not ticket or len(ticket) > 4096:
        raise HTTPException(401)
    try:
        response = await http.post(
            f"{API}/api/v1/media/{asset_id}/stream-authorize",
            json={"ticket": ticket}, headers={"X-Streaming-Secret": SECRET},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Authorization service unavailable")
    if response.status_code != 200:
        raise HTTPException(403 if response.status_code in (401, 403, 404) else 503)
    ref = response.json()
    msg = await client.get_messages(int(ref["chat_id"]), ids=int(ref["message_id"]))
    if not msg or not msg.file or not msg.document:
        raise HTTPException(404)
    size = msg.file.size
    if not size or size < 1:
        raise HTTPException(404)
    mime = getattr(msg.file, "mime_type", None) or "application/octet-stream"
    if mime not in ("video/mp4", "video/webm", "video/x-matroska"):
        raise HTTPException(415, "Media format is not browser-playable")
    raw_range = request.headers.get("range")
    start, end = 0, min(size - 1, MAX_RANGE - 1)
    if raw_range:
        match = RANGE.fullmatch(raw_range.strip())
        if not match:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        start = int(match.group(1))
        requested_end = int(match.group(2)) if match.group(2) else size - 1
        if start >= size or requested_end < start:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        end = min(requested_end, start + MAX_RANGE - 1, size - 1)
    length = end - start + 1

    async def chunks():
        remaining = length
        # iter_download supports unaligned offsets; limit is expressed in chunks.
        async for chunk in client.iter_download(msg.media, offset=start, request_size=512 * 1024,
                                                chunk_size=512 * 1024):
            if await request.is_disconnected():
                break
            data = bytes(chunk[:remaining])
            if data:
                yield data
                remaining -= len(data)
            if remaining <= 0:
                break

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length),
               "Cache-Control": "private, no-store", "Access-Control-Allow-Origin": ORIGIN,
               "Vary": "Origin", "X-Content-Type-Options": "nosniff",
               "Referrer-Policy": "no-referrer"}
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(chunks(), status_code=206,
                             media_type=mime, headers=headers)
