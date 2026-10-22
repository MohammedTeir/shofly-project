from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from tgbot import callbacks as cb
from tgbot import screens as sc
from tgbot import keyboards as kb
from tgbot.formatting import asset_label
import html
from tgbot.api import ApiError
from tgbot.localization import t

async def deliver_file(bot, api, session, user_id: int, asset_id: str) -> str:
    """Returns the localized message key. The backend re-checks the full delivery policy on every call."""
    try:
        ref = await api.telegram_delivery(session.token, asset_id)
    except ApiError as e:
        if e.status in (400, 403, 404):
            return "delivery_denied"
        raise
    parts = ref.get("parts") or [{"chat_id": ref["chat_id"], "message_id": ref["message_id"]}]
    if not isinstance(parts, list) or not parts or len(parts) > 500:
        return "delivery_failed"
    try:  # copy (no 'forwarded from' header) and block forwarding/saving; not a perfect anti-copy measure
        for part in parts:
            await bot.copy_message(chat_id=user_id, from_chat_id=part["chat_id"],
                                   message_id=part["message_id"], protect_content=True)
    except TelegramAPIError:
        return "delivery_failed"
    return "sending"


def make_router() -> Router:
    router = Router()
    @router.callback_query(F.data.startswith("bw:"))
    async def browse(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        text, markup = await sc.list_screen(api, session, p[1], p[2])
        await sc.show(c, text, markup)


    @router.callback_query(F.data.startswith("it:"))
    async def item(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        text, markup = await sc.item_screen(api, session, p[1], p[2])
        await sc.show(c, text, markup)


    @router.callback_query(F.data.startswith("se:"))
    async def season(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        text, markup = await sc.season_screen(api, session, p[1], p[2])
        await sc.show(c, text, markup)


    @router.callback_query(F.data.startswith("fl:"))
    async def favlist(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        text, markup = await sc.favorites_screen(api, session, p[1])
        await sc.show(c, text, markup)


    @router.callback_query(F.data.startswith("fv:"))
    async def favorite(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        await api.set_favorite(session.token, p[1], p[2], p[3])
        text, markup = await sc.item_screen(api, session, p[1], p[2])
        await sc.show(c, text, markup, toast=t(session.lang, "fav_saved" if p[3] else "fav_removed"))

    @router.callback_query(F.data.startswith("ql:"))
    async def movie_qualities(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p or p[1] != "movie":
            return await c.answer()
        item = await api.title(session.token, "movie", p[2])
        assets = item.get("assets") or []
        title = html.escape(item.get("title") or "")
        heading = f"🎬 <b>{title}</b>\n\n🎞 <b>اختر جودة الفيديو</b>\nاضغط على الجودة المناسبة لإرسال الملف إليك مباشرة.\n\n📦 الأحجام الفعلية موضحة بجانب كل جودة." if session.lang == "ar" else f"🎬 <b>{title}</b>\n\n🎞 <b>Choose video quality</b>\nTap a quality to receive the file.\n\n📦 Actual file sizes are shown."
        await sc.show(c, heading if assets else ("لا توجد جودات متاحة حاليًا." if session.lang == "ar" else "No qualities available."), kb.quality_kb(assets, session.lang, cb.item_cb("movie", p[2])))

    @router.callback_query(F.data.startswith("qe:"))
    async def episode_qualities(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        result = await api.episode_qualities(session.token, p[1])
        assets = result.get("assets") or []
        season = result.get("season_number", 0)
        title = html.escape(result.get("title") or f"Episode {result.get('episode_number', '')}")
        heading = f"📺 <b>{title}</b> · S{season}E{result.get('episode_number', 0)}\n\n🎞 <b>اختر جودة الحلقة</b>\n📦 اضغط على الجودة لإرسال الملف إليك." if session.lang == "ar" else f"📺 <b>{title}</b> · S{season}E{result.get('episode_number', 0)}\n\n🎞 <b>Choose episode quality</b>\n📦 Tap to receive the file."
        await sc.show(c, heading if assets else ("لا توجد جودات متاحة حاليًا." if session.lang == "ar" else "No qualities available."), kb.quality_kb(assets, session.lang, cb.season_cb(str(result["series_id"]), season)))

    @router.callback_query(F.data.startswith("dl:"))
    async def download(c: CallbackQuery, api, session, bot):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        await c.answer(t(session.lang, await deliver_file(bot, api, session, c.from_user.id, p[1])), show_alert=False)

    return router
