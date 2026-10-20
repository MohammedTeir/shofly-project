import hashlib, hmac, json, time
from urllib.parse import parse_qsl
from app.core.errors import AppError


def _bad():
    return AppError(401, "INVALID_INIT_DATA", "Invalid Telegram data.")


def verify_init_data(init_data: str, bot_token: str, max_age: int) -> dict:
    """Verify Telegram WebApp initData (HMAC-SHA256 + auth_date freshness). Returns the user dict."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        raise _bad()
    received = pairs.pop("hash", None)
    if not received:
        raise _bad()
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise _bad()
    try:
        auth_date = int(pairs["auth_date"])
        user = json.loads(pairs["user"])
        int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise _bad()
    age = time.time() - auth_date
    if age > max_age or age < -60:
        raise AppError(401, "INIT_DATA_EXPIRED", "Telegram session expired. Reopen the app.")
    return user
