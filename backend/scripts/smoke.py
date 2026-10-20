"""Post-deploy smoke test: python -m scripts.smoke https://api.example.com   (exit code 1 on any failure)"""
import json
import sys
import urllib.error
import urllib.request


def get(base, path, method="GET", data=None, headers=None):
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main(base: str) -> int:
    base = base.rstrip("/")
    checks = [
        ("liveness", lambda: get(base, "/health/live")[0] == 200),
        ("readiness (database reachable)", lambda: get(base, "/health/ready")[0] == 200),
        ("openapi served", lambda: "paths" in json.loads(get(base, "/openapi.json")[2])),
        ("auth required on /me", lambda: get(base, "/api/v1/me")[0] == 401),
        ("request id header present", lambda: "x-request-id" in {k.lower() for k in get(base, "/api/v1/me")[1]}),
        ("worker endpoint rejects no token", lambda: get(base, "/api/v1/worker/ping")[0] == 401),
        ("admin endpoint rejects no token", lambda: get(base, "/api/v1/admin/overview")[0] == 401),
        ("forged Telegram login rejected", lambda: get(base, "/api/v1/auth/telegram", "POST",
                                                       json.dumps({"init_data": "auth_date=1&hash=00"}).encode(),
                                                       {"Content-Type": "application/json"})[0] == 401),
    ]
    failed = 0
    for name, fn in checks:
        try:
            ok = fn()
        except Exception as e:  # noqa: BLE001
            ok = False; name += f" ({type(e).__name__})"
        print(("PASS " if ok else "FAIL ") + name); failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
