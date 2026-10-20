# TML Telegram bot (aiogram 3)

Setup: `pip install -r requirements.txt && cp .env.example .env` (fill TELEGRAM_BOT_TOKEN, BOT_API_TOKEN, API_BASE_URL)
Run (long polling, dev): `python -m tgbot.main` · Test: `python -m pytest -q` (needs ../../backend importable; tests run it in-process)

Backend must have the same `BOT_API_TOKEN`. The bot logs users in via `POST /api/v1/bot/auth` using the verified
Telegram sender; the shared secret must stay server-side.

Implemented: /start, /help, /language (+ persistent preference shared with the Mini App), /browse, /search (or plain text),
/favorites, inline pagination, favorites toggle, series seasons/episodes, Mini App button (HTTPS only), per-user throttle,
localized (ar/en) menus, errors and command lists.
Not implemented: /request, /myrequests, /myplan, /report (Milestones 6-7), file delivery (Milestone 4), webhook mode,
deep links, notifications. Verified only against a faked Telegram transport, never a live bot.
