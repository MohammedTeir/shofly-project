"""Bounded, validated callback_data (Telegram limit: 64 bytes). Never trust it: the server re-checks access."""
import re
import uuid

KIND = {"m": "movie", "s": "series"}
CODE = {v: k for k, v in KIND.items()}
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def lang_cb(lang: str) -> str: return f"lang:{lang}"
def menu_cb(name: str) -> str: return f"menu:{name}"
def item_cb(kind: str, item_id: str) -> str: return f"it:{CODE[kind]}:{item_id}"
def browse_cb(kind: str, offset: int) -> str: return f"bw:{CODE[kind]}:{offset}"
def fav_cb(kind: str, item_id: str, on: bool) -> str: return f"fv:{CODE[kind]}:{item_id}:{int(on)}"
def favlist_cb(offset: int) -> str: return f"fl:{offset}"
def dl_cb(asset_id: str) -> str: return f"dl:{asset_id}"
def season_cb(series_id: str, n: int) -> str: return f"se:{series_id}:{n}"


def _uuid(v: str) -> str | None:
    try:
        return str(uuid.UUID(v))
    except ValueError:
        return None


def parse(data: str | None):
    """Return a tuple (action, *args) or None for anything malformed."""
    if not data or len(data.encode()) > 64:
        return None
    p = data.split(":")
    try:
        if p[0] == "lang" and len(p) == 2 and LANG_RE.match(p[1]):
            return ("lang", p[1])
        if p[0] == "menu" and len(p) == 2 and p[1] in {"browse", "search", "favorites", "language"}:
            return ("menu", p[1])
        if p[0] == "it" and len(p) == 3 and p[1] in KIND and _uuid(p[2]):
            return ("it", KIND[p[1]], p[2])
        if p[0] == "bw" and len(p) == 3 and p[1] in KIND and 0 <= int(p[2]) <= 100000:
            return ("bw", KIND[p[1]], int(p[2]))
        if p[0] == "fv" and len(p) == 4 and p[1] in KIND and _uuid(p[2]) and p[3] in {"0", "1"}:
            return ("fv", KIND[p[1]], p[2], p[3] == "1")
        if p[0] == "fl" and len(p) == 2 and 0 <= int(p[1]) <= 100000:
            return ("fl", int(p[1]))
        if p[0] == "dl" and len(p) == 2 and _uuid(p[1]):
            return ("dl", p[1])
        if p[0] == "se" and len(p) == 3 and _uuid(p[1]) and 0 <= int(p[2]) <= 999:
            return ("se", p[1], int(p[2]))
    except ValueError:
        return None
    return None
