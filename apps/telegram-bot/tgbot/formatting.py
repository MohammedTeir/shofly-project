import html
from tgbot.localization import t

ICON = {"movie": "🎬", "series": "📺"}


def item_label(item: dict) -> str:
    year = f" ({item['year']})" if item.get("year") else ""
    return f"{ICON[item['kind']]} {item['title']}{year}"[:56]


def detail_text(item: dict, lang: str) -> str:
    lines = [f"<b>{html.escape(item['title'])}</b>"]
    if item.get("year"):
        lines[0] += f" ({item['year']})"
    if item["original_title"] != item["title"]:
        lines.append(f"{t(lang, 'original_title')}: {html.escape(item['original_title'])}")
    if item.get("synopsis"):
        syn = item["synopsis"]
        lines += ["", html.escape(syn if len(syn) <= 700 else syn[:697] + "…")]
    if item["kind"] == "movie" and not item.get("assets"):
        lines += ["", f"<i>{t(lang, 'delivery_pending')}</i>"]
    return "\n".join(lines)


def episodes_text(data: dict, lang: str) -> str:
    n = data["season_number"]
    head = t(lang, "specials") if n == 0 else t(lang, "season_label", n=n)
    if not data["episodes"]:
        return f"<b>{head}</b>\n{t(lang, 'episodes_empty')}"
    rows = [f"{e['episode_number']}. {html.escape(e['title'] or '—')}" for e in data["episodes"]]
    return f"<b>{head}</b>\n" + "\n".join(rows)


def asset_label(a: dict) -> str:
    size = a.get("size_bytes") or 0
    human = f"{size / 1073741824:.1f} GB" if size >= 1073741824 else f"{size / 1048576:.0f} MB"
    return " · ".join(x for x in (a.get("quality"), human) if x)
