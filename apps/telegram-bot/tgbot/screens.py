import html
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from tgbot import callbacks as cb
from tgbot import keyboards as kb
from tgbot.api import BotApi
from tgbot.formatting import detail_text, episodes_text
from tgbot.localization import t

PAGE = 8


async def show(event, text: str, markup=None, toast: str | None = None):
    """Edit in place for callbacks (answering the query exactly once), send a new message otherwise."""
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(text, reply_markup=markup)
            except TelegramBadRequest as e:
                if "not modified" not in str(e):
                    raise
        await event.answer(toast)
    else:
        await event.answer(text, reply_markup=markup)


async def list_screen(api: BotApi, s, kind: str, offset: int):
    data = await api.list_titles(s.token, kind, offset, PAGE)
    back = kb.back_row(s.lang, cb.menu_cb("browse"))
    if not data["items"]:
        return t(s.lang, "browse_empty"), kb.items_kb([], [back])
    nxt = int(data["next_cursor"]) if data["next_cursor"] else None
    nav = kb.nav_row(s.lang, cb.browse_cb(kind, max(0, offset - PAGE)) if offset > 0 else None,
                     cb.browse_cb(kind, nxt) if nxt is not None else None)
    return t(s.lang, "movies" if kind == "movie" else "series"), kb.items_kb(data["items"], [r for r in (nav, back) if r])


async def search_screen(api: BotApi, s, q: str):
    q = q.strip()[:100]
    data = await api.search(s.token, q, PAGE)
    if not data["items"]:
        return t(s.lang, "no_results", q=html.escape(q)), None
    return t(s.lang, "results_title", q=html.escape(q)), kb.items_kb(data["items"])


async def item_screen(api: BotApi, s, kind: str, item_id: str):
    item = await api.title(s.token, kind, item_id)
    return detail_text(item, s.lang), kb.detail_kb(item, s.lang)


async def season_screen(api: BotApi, s, series_id: str, n: int):
    data = await api.season(s.token, series_id, n)
    return episodes_text(data, s.lang), kb.episodes_kb(s.lang, data, cb.item_cb("series", series_id))


async def favorites_screen(api: BotApi, s, offset: int):
    data = await api.favorites(s.token, offset, PAGE)
    back = kb.back_row(s.lang, cb.menu_cb("browse"))
    if not data["items"]:
        return t(s.lang, "favorites_empty"), None
    nxt = int(data["next_cursor"]) if data["next_cursor"] else None
    nav = kb.nav_row(s.lang, cb.favlist_cb(max(0, offset - PAGE)) if offset > 0 else None,
                     cb.favlist_cb(nxt) if nxt is not None else None)
    return t(s.lang, "favorites_title"), kb.items_kb(data["items"], [nav] if nav else [])
