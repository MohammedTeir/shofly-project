import uuid
from aiogram.types import InlineKeyboardMarkup
from tgbot import callbacks as cb
from tgbot.formatting import asset_label, detail_text, episodes_text, item_label
from tgbot.keyboards import detail_kb, main_menu
from tgbot.localization import STRINGS, t
import string


def fields(s): return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def test_languages_have_identical_keys_and_placeholders():
    assert STRINGS["ar"].keys() == STRINGS["en"].keys()
    for k in STRINGS["en"]:
        assert STRINGS["en"][k].strip() and STRINGS["ar"][k].strip()
        assert fields(STRINGS["en"][k]) == fields(STRINGS["ar"][k]), k


def test_unknown_language_falls_back_to_default():
    assert t("fr", "back") == STRINGS["ar"]["back"]


def test_callbacks_roundtrip_fit_64_bytes_and_reject_garbage():
    i = str(uuid.uuid4())
    samples = [cb.lang_cb("ar"), cb.menu_cb("browse"), cb.item_cb("movie", i), cb.browse_cb("series", 16),
               cb.fav_cb("series", i, True), cb.favlist_cb(8), cb.season_cb(i, 12), cb.dl_cb(i)]
    assert all(len(s.encode()) <= 64 for s in samples) and all(cb.parse(s) for s in samples)
    assert cb.parse(cb.fav_cb("movie", i, False)) == ("fv", "movie", i, False)
    for bad in [None, "", "it:m:not-a-uuid", "bw:m:-1", "bw:x:1", "lang:../../x", "menu:admin", "fv:m:" + i + ":2", "x" * 100, "se:" + i + ":9999"]:
        assert cb.parse(bad) is None, bad


def test_detail_text_escapes_html_and_truncates():
    item = {"kind": "movie", "title": "<b>Bad&</b>", "original_title": "Orig", "year": 2020, "synopsis": "x" * 900}
    out = detail_text(item, "en")
    assert "&lt;b&gt;Bad&amp;&lt;/b&gt;" in out and "Original title: Orig" in out and "…" in out
    assert len(item_label({"kind": "movie", "title": "T" * 100, "year": 1})) <= 56


def test_episodes_text_specials_and_empty():
    assert "حلقات خاصة" in episodes_text({"season_number": 0, "episodes": []}, "ar")
    assert "1. Pilot" in episodes_text({"season_number": 1, "episodes": [{"episode_number": 1, "title": "Pilot"}]}, "en")


def test_miniapp_button_only_for_https():
    def has_web(m): return any(b.web_app for r in m.inline_keyboard for b in r)
    assert not has_web(main_menu("en", None)) and not has_web(main_menu("en", "http://x")) and has_web(main_menu("en", "https://x.app"))


def test_detail_kb_toggle_and_seasons():
    i = str(uuid.uuid4())
    m = detail_kb({"kind": "series", "id": i, "favorited": True, "seasons": [{"season_number": 0}, {"season_number": 1}]}, "en")
    datas = [b.callback_data for r in m.inline_keyboard for b in r]
    assert cb.fav_cb("series", i, False) in datas and cb.season_cb(i, 0) in datas and cb.season_cb(i, 1) in datas


def test_asset_label_and_delivery_note():
    assert asset_label({"quality": "1080p", "size_bytes": 3 * 1073741824}) == "1080p · 3.0 GB"
    assert asset_label({"quality": None, "size_bytes": 5 * 1048576}) == "5 MB"
    base = {"kind": "movie", "title": "T", "original_title": "T"}
    assert "No downloadable file" in detail_text(base, "en") and "No downloadable file" not in detail_text({**base, "assets": [{"id": "x"}]}, "en")
    assert cb.parse("dl:not-a-uuid") is None
