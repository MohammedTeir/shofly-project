import html
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from tgbot import callbacks as cb
from tgbot import keyboards as kb
from tgbot import screens as sc
from tgbot.localization import t
from tgbot.handlers.catalog import deliver_file

def make_router() -> Router:
    router = Router()
    @router.message(CommandStart())
    async def start(m: Message, command: CommandObject, session, settings, api, bot):
        arg = command.args or ""
        if arg.startswith("dl_") and len(arg) == 35:  # deep link from the Mini App: dl_<asset uuid hex>
            try:
                asset_id = str(__import__("uuid").UUID(hex=arg[3:]))
            except ValueError:
                asset_id = None
            if asset_id:
                key = await deliver_file(bot, api, session, m.from_user.id, asset_id)
                if key != "sending":
                    await sc.show(m, t(session.lang, key))
                return
        name = html.escape(m.from_user.first_name or "")
        await sc.show(m, t(session.lang, "welcome", name=name), kb.main_menu(session.lang, settings.public_app_url))


    @router.message(Command("help"))
    async def help_(m: Message, session):
        await sc.show(m, t(session.lang, "help"))


    @router.message(Command("language"))
    async def language(m: Message, session):
        await sc.show(m, t(session.lang, "choose_language"), kb.language_kb())


    @router.message(Command("browse"))
    async def browse(m: Message, session):
        await sc.show(m, t(session.lang, "browse_title"), kb.browse_menu(session.lang))


    @router.message(Command("search"))
    async def search_cmd(m: Message, command: CommandObject, api, session):
        if not command.args:
            return await sc.show(m, t(session.lang, "search_prompt"))
        text, markup = await sc.search_screen(api, session, command.args)
        await sc.show(m, text, markup)


    @router.message(Command("favorites"))
    async def favorites(m: Message, api, session):
        text, markup = await sc.favorites_screen(api, session, 0)
        await sc.show(m, text, markup)


    @router.callback_query(F.data.startswith("lang:"))
    async def set_lang(c: CallbackQuery, api, session, settings):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        res = await api.set_language(session.token, p[1])  # same preference service as the Mini App
        session.lang = res["preferred_language"]
        await sc.show(c, t(session.lang, "language_saved"), kb.main_menu(session.lang, settings.public_app_url))


    @router.callback_query(F.data.startswith("menu:"))
    async def menu(c: CallbackQuery, api, session):
        p = cb.parse(c.data)
        if not p:
            return await c.answer()
        if p[1] == "browse":
            await sc.show(c, t(session.lang, "browse_title"), kb.browse_menu(session.lang))
        elif p[1] == "language":
            await sc.show(c, t(session.lang, "choose_language"), kb.language_kb())
        elif p[1] == "search":
            await sc.show(c, t(session.lang, "search_prompt"))
        else:
            text, markup = await sc.favorites_screen(api, session, 0)
            await sc.show(c, text, markup)


    @router.message(F.text & ~F.text.startswith("/"))
    async def plain_text_search(m: Message, api, session):
        text, markup = await sc.search_screen(api, session, m.text)
        await sc.show(m, text, markup)
    return router
