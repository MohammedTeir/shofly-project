from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M, WebAppInfo
from tgbot import callbacks as cb
from tgbot.formatting import asset_label, item_label
from tgbot.localization import t

LANGS = [("ar", "العربية"), ("en", "English")]


def main_menu(lang: str, app_url: str | None) -> M:
    rows = [[B(text=t(lang, "menu_browse"), callback_data=cb.menu_cb("browse")),
             B(text=t(lang, "menu_search"), callback_data=cb.menu_cb("search"))],
            [B(text=t(lang, "menu_favorites"), callback_data=cb.menu_cb("favorites")),
             B(text=t(lang, "menu_language"), callback_data=cb.menu_cb("language"))]]
    if app_url and app_url.startswith("https://"):  # Telegram requires HTTPS for Mini Apps
        rows.append([B(text=t(lang, "menu_open"), web_app=WebAppInfo(url=app_url))])
    return M(inline_keyboard=rows)


def language_kb() -> M:
    return M(inline_keyboard=[[B(text=name, callback_data=cb.lang_cb(code)) for code, name in LANGS]])


def browse_menu(lang: str) -> M:
    return M(inline_keyboard=[[B(text=t(lang, "movies"), callback_data=cb.browse_cb("movie", 0)),
                               B(text=t(lang, "series"), callback_data=cb.browse_cb("series", 0))]])


def items_kb(items: list[dict], extra_rows: list[list[B]] | None = None) -> M:
    rows = [[B(text=item_label(i), callback_data=cb.item_cb(i["kind"], str(i["id"])))] for i in items]
    return M(inline_keyboard=rows + (extra_rows or []))


def nav_row(lang: str, prev_cb: str | None, next_cb: str | None) -> list[B]:
    row = []
    if prev_cb:
        row.append(B(text=t(lang, "prev"), callback_data=prev_cb))
    if next_cb:
        row.append(B(text=t(lang, "next"), callback_data=next_cb))
    return row


def back_row(lang: str, data: str) -> list[B]:
    return [B(text=t(lang, "back"), callback_data=data)]


def detail_kb(item: dict, lang: str) -> M:
    kind, iid = item["kind"], str(item["id"])
    fav = item.get("favorited", False)
    rows = [[B(text=f"{t(lang, 'send_file')} ({asset_label(a)})", callback_data=cb.dl_cb(str(a["id"])))] for a in item.get("assets", [])[:4]]
    rows.append([B(text=t(lang, "fav_remove" if fav else "fav_add"), callback_data=cb.fav_cb(kind, iid, not fav))])
    for s in item.get("seasons", []):
        n = s["season_number"]
        label = t(lang, "specials") if n == 0 else t(lang, "season_label", n=n)
        rows.append([B(text=label, callback_data=cb.season_cb(iid, n))])
    rows.append(back_row(lang, cb.browse_cb(kind, 0)))
    return M(inline_keyboard=rows)


def episodes_kb(lang: str, data: dict, back_data: str) -> M:
    rows = [[B(text=f"📥 {data['season_number'] and 'S' + str(data['season_number']) or '★'}E{e['episode_number']} · {asset_label(e['assets'][0])}",
               callback_data=cb.dl_cb(str(e["assets"][0]["id"])))] for e in data["episodes"] if e.get("assets")][:40]
    return M(inline_keyboard=rows + [back_row(lang, back_data)])
