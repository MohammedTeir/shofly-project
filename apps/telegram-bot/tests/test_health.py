import asyncio
import json
from tgbot.main import HEALTH_BODY, health_handler


def test_health_listener_returns_valid_http_with_correct_content_length():
    async def go():
        server = await asyncio.start_server(health_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n"); await w.drain()
        raw = await asyncio.wait_for(r.read(), 3)
        w.close(); server.close(); await server.wait_closed()
        head, _, body = raw.partition(b"\r\n\r\n")
        assert head.startswith(b"HTTP/1.1 200")
        assert int(next(l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length"))) == len(body)
        assert json.loads(body) == {"status": "ok"} and body == HEALTH_BODY
    asyncio.run(go())
