import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from tgbot.api import BotApi
from tgbot.config import BotSettings
from tgbot.handlers import catalog, common
from tgbot.localization import t
from tgbot.middleware import AuthMiddleware, ThrottleMiddleware

COMMANDS = ["start", "browse", "search", "favorites", "language", "help"]


def build_dispatcher(api: BotApi, settings: BotSettings) -> Dispatcher:
    dp = Dispatcher()
    dp["api"], dp["settings"] = api, settings
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(AuthMiddleware(api))  # registered first -> runs first
    # one throttle instance shared by both observers
    throttle = ThrottleMiddleware(settings.throttle_max, settings.throttle_window)
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)
    dp.include_router(common.make_router())
    dp.include_router(catalog.make_router())
    return dp


async def set_commands(bot: Bot):
    for code, lang in ((None, "ar"), ("ar", "ar"), ("en", "en")):
        await bot.set_my_commands([BotCommand(command=c, description=t(lang, f"cmd_{c}")) for c in COMMANDS],
                                  language_code=code)


async def main():
    logging.basicConfig(level=logging.INFO)
    s = BotSettings()
    api = BotApi(s.api_base_url, s.bot_api_token)
    bot = Bot(s.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(api, s)
    await set_commands(bot)
    try:
        await dp.start_polling(bot)  # dev: long polling. Webhook mode: pending.
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
