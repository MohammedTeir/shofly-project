"""End-to-end: aiogram Dispatcher -> BotApi -> real backend app (in-process, SQLite). Telegram itself is faked."""
import asyncio
from datetime import datetime
import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, CopyMessage, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User
from app.fixtures import make_visible
from app.core.crypto import encrypt
from app.models import ContentRight, MediaAsset
from app.models import Episode, Movie, Season, TvSeries, User as DbUser
from tgbot.api import ApiError
from tgbot.config import BotSettings
from tgbot.localization import t
from tgbot.main import build_dispatcher


class Capture(BaseSession):
    def __init__(self):
        super().__init__(); self.calls = []

    async def close(self): ...
    async def stream_content(self, *a, **k): yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=1, type="private"), text="x")

    def texts(self): return [c.text for c in self.calls if isinstance(c, (SendMessage, EditMessageText))]
    def last(self): return [c for c in self.calls if isinstance(c, (SendMessage, EditMessageText))][-1]


def settings(**kw):
    return BotSettings(telegram_bot_token="123456:TESTTOKEN", bot_api_token="bot-secret-token", **kw)


class Harness:
    def __init__(self, api, **kw):
        self.session = Capture()
        self.bot = Bot("123456:TESTTOKEN", session=self.session)
        self.dp = build_dispatcher(api, settings(**kw))
        self.n = 0

    async def say(self, user, text):
        self.n += 1
        ents = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))] if text.startswith("/") else None
        msg = Message(message_id=self.n, date=datetime.now(), chat=Chat(id=user.id, type="private"), from_user=user, text=text, entities=ents)
        await self.dp.feed_update(self.bot, Update(update_id=self.n, message=msg))

    async def tap(self, user, data):
        self.n += 1
        msg = Message(message_id=self.n, date=datetime.now(), chat=Chat(id=user.id, type="private"), text="menu")
        await self.dp.feed_update(self.bot, Update(update_id=self.n, callback_query=CallbackQuery(
            id=str(self.n), from_user=user, chat_instance="c", message=msg, data=data)))


EN = User(id=1, is_bot=False, first_name="Sam", language_code="en")
AR = User(id=2, is_bot=False, first_name="سلمى", language_code="ar")


def test_start_is_localized_from_telegram_locale(make_api):
    async def go():
        h = Harness(make_api())
        await h.say(EN, "/start"); await h.say(AR, "/start")
        assert t("en", "welcome", name="Sam") in h.session.texts()[0]
        assert "أهلاً" in h.session.texts()[1]
    asyncio.run(go())


def test_language_choice_persists_and_survives_changed_telegram_locale(make_api, db):
    async def go():
        h = Harness(make_api())
        await h.say(EN, "/start")
        await h.tap(EN, "lang:ar")
        assert h.session.texts()[-1] == t("ar", "language_saved")
        # a fresh bot process/cache, Telegram now says "en" again -> server preference wins
        h2 = Harness(make_api())
        await h2.say(EN, "/help")
        assert h2.session.texts()[-1] == t("ar", "help")
    asyncio.run(go())
    assert db.query(DbUser).one().language_source == "user"


def test_search_open_favorite_and_series_seasons(make_api, db):
    m = Movie(original_title="Interstellar", release_year=2014, status="published")
    s = TvSeries(original_title="Sample Series", status="published"); db.add_all([m, s]); db.flush()
    se = Season(series_id=s.id, season_number=1); db.add(se); db.flush()
    db.add(Episode(season_id=se.id, episode_number=1, title="Pilot")); db.commit(); make_visible(db, m, s)

    async def go():
        h = Harness(make_api())
        await h.say(EN, "inter")  # plain text = search
        kb = h.session.last().reply_markup.inline_keyboard
        assert kb[0][0].callback_data == f"it:m:{m.id}" and "Interstellar (2014)" in kb[0][0].text
        await h.tap(EN, kb[0][0].callback_data)
        assert "Interstellar" in h.session.last().text
        await h.tap(EN, f"fv:m:{m.id}:1")
        assert any(b.text == t("en", "fav_remove") for r in h.session.last().reply_markup.inline_keyboard for b in r)
        await h.say(EN, "/favorites")
        assert h.session.last().reply_markup.inline_keyboard[0][0].callback_data == f"it:m:{m.id}"
        await h.tap(EN, f"it:s:{s.id}")
        await h.tap(EN, f"se:{s.id}:1")
        assert "1. Pilot" in h.session.last().text
        await h.say(EN, "/search zzzz")
        assert h.session.last().text == t("en", "no_results", q="zzzz")
    asyncio.run(go())


def test_unpublished_and_garbage_callbacks_are_safe(make_api, db):
    d = Movie(original_title="Hidden", status="draft"); db.add(d); db.commit()

    async def go():
        h = Harness(make_api())
        await h.tap(EN, f"it:m:{d.id}")
        assert h.session.last().text == t("en", "not_found")
        before = len(h.session.calls)
        await h.tap(EN, "it:m:not-a-uuid")  # ignored, just answers the callback
        assert len(h.session.calls) == before + 1 and isinstance(h.session.calls[-1], AnswerCallbackQuery)
    asyncio.run(go())


def test_wrong_bot_secret_is_rejected_and_backend_down_is_handled(make_api):
    async def go():
        with pytest.raises(ApiError) as e:
            await make_api("wrong").auth({"id": 9})
        assert e.value.status == 401
        h = Harness(make_api("wrong"))
        await h.say(EN, "/start")
        assert h.session.texts()[-1] == t(None, "error")  # generic error, no secrets leaked
    asyncio.run(go())


def test_throttle_warns_once_then_drops(make_api):
    async def go():
        h = Harness(make_api(), throttle_max=3, throttle_window=60)
        for _ in range(6):
            await h.say(EN, "/help")
        texts = h.session.texts()
        assert texts.count(t("en", "help")) == 3 and texts.count(t("en", "throttled")) == 1
    asyncio.run(go())


def tg_movie(db, **right):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    m = Movie(original_title="Owned Film", status="published", metadata_verified=True); db.add(m); db.flush()
    a = MediaAsset(movie_id=m.id, provider="telegram", provider_ref_encrypted=encrypt("-1009:42:FID"), size_bytes=3 * 1048576,
                   checksum_sha256="e" * 64, quality="1080p", upload_status="verified"); db.add(a)
    kw = dict(content_kind="movie", content_id=m.id, license_type="o", proof_ref_encrypted="x", telegram_allowed=True, territories=["ALL"],
              valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=5), review_status="APPROVED"); kw.update(right)
    db.add(ContentRight(**kw)); db.commit()
    return m, a


def copies(h): return [c for c in h.session.calls if isinstance(c, CopyMessage)]


def test_send_file_button_copies_from_storage_with_forward_protection(make_api, db):
    m, a = tg_movie(db)

    async def go():
        h = Harness(make_api())
        await h.tap(EN, f"it:m:{m.id}")
        buttons = [b for r in h.session.last().reply_markup.inline_keyboard for b in r]
        choose = next(b for b in buttons if b.callback_data == f"ql:m:{m.id}")
        await h.tap(EN, choose.callback_data)
        quality_buttons = [b for r in h.session.last().reply_markup.inline_keyboard for b in r]
        send = next(b for b in quality_buttons if b.callback_data == f"dl:{a.id}")
        assert "1080p" in send.text and "3 MB" in send.text and "FID" not in str(h.session.last())
        await h.tap(EN, send.callback_data)
        (c,) = copies(h)
        assert (c.chat_id, c.from_chat_id, c.message_id, c.protect_content) == (EN.id, -1009, 42, True)
        assert [x for x in h.session.calls if isinstance(x, AnswerCallbackQuery)][-1].text == t("en", "sending")
    asyncio.run(go())


def test_deep_link_from_mini_app_delivers(make_api, db):
    m, a = tg_movie(db)

    async def go():
        h = Harness(make_api())
        await h.say(EN, f"/start dl_{a.id.hex}")
        assert len(copies(h)) == 1 and not h.session.texts()  # no welcome spam: just the file
        await h.say(EN, "/start dl_" + "0" * 32)  # unknown asset
        assert len(copies(h)) == 1 and h.session.texts()[-1] == t("en", "delivery_denied")
        await h.say(EN, "/start dl_zzzz")  # malformed -> normal welcome
        assert "Welcome" in h.session.texts()[-1]
    asyncio.run(go())


def test_delivery_denied_when_rights_revoked_even_with_stale_button(make_api, db):
    m, a = tg_movie(db)

    async def go():
        h = Harness(make_api())
        await h.tap(EN, f"it:m:{m.id}")
        db.query(ContentRight).update({"review_status": "REVOKED"}); db.commit()  # takedown after the button was shown
        await h.tap(EN, f"dl:{a.id}")
        assert copies(h) == []
        assert [x for x in h.session.calls if isinstance(x, AnswerCallbackQuery)][-1].text == t("en", "delivery_denied")
    asyncio.run(go())


def test_storage_error_is_reported_without_details(make_api, db):
    m, a = tg_movie(db)
    from aiogram.exceptions import TelegramBadRequest

    async def go():
        h = Harness(make_api())
        orig = h.session.make_request

        async def failing(bot, method, timeout=None):
            if isinstance(method, CopyMessage):
                raise TelegramBadRequest(method=method, message="message to copy not found")
            return await orig(bot, method, timeout)
        h.session.make_request = failing
        await h.tap(EN, f"dl:{a.id}")
        assert [x for x in h.session.calls if isinstance(x, AnswerCallbackQuery)][-1].text == t("en", "delivery_failed")
    asyncio.run(go())
