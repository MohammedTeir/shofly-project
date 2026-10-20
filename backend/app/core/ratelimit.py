import time
from collections import defaultdict, deque
from fastapi import Request
from app.core.errors import AppError


class RateLimiter:
    """In-process sliding window. Single-instance only; swap for Redis/DB when scaling out."""
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def reset(self):
        self.hits.clear()

    def check(self, key: str, limit: int, window: int):
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise AppError(429, "RATE_LIMITED", "Too many requests. Try again shortly.")
        q.append(now)


limiter = RateLimiter()


def rate_limit(name: str, limit: int, window: int = 60):
    def dep(request: Request):
        ip = request.client.host if request.client else "unknown"
        limiter.check(f"{name}:{ip}", limit, window)
    return dep
