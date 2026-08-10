"""
Tests for command_router.route — the deterministic, regex-heavy pre-LLM router.

This is the most fragile module (small regex changes have caused real routing
bugs), so it gets the most coverage. Pure logic, no network / GPU / model.

Run:  pytest
"""

import pytest

from command_router import route


def _type(text, lang="tr"):
    r = route(text, lang)
    return r["type"] if r else None


def _payload(text, lang="tr"):
    r = route(text, lang)
    return r["payload"] if r else None


# --- Power vs. app: "restart X" must not reboot the PC (regression) ----------

@pytest.mark.parametrize("text", [
    "bilgisayarı yeniden başlat",
    "pc'yi yeniden başlat",
    "makineyi yeniden başlat",
    "sistemi resetle",
])
def test_tr_restart_pc_context_routes_power(text):
    assert _type(text) == "POWER"


@pytest.mark.parametrize("text", [
    "spotify'ı yeniden başlat",   # app, not the machine
    "discord yeniden başlat",
])
def test_tr_restart_app_is_not_power(text):
    assert _type(text) != "POWER"


@pytest.mark.parametrize("text,expected", [
    ("restart the computer", "POWER"),
    ("reboot", "POWER"),
    ("restart spotify", None),      # no PC context -> defer to LLM, don't reboot
])
def test_en_restart_context(text, expected):
    assert _type(text, "en") == expected


# --- Shutdown needs PC context ----------------------------------------------

def test_tr_shutdown_pc():
    assert _type("bilgisayarı kapat") == "POWER"


def test_tr_close_app_not_power():
    assert _type("chrome'u kapat") == "CLOSE"


# --- Media: bare play/stop must not fire on conversation (regression) --------

@pytest.mark.parametrize("text", [
    "can you play a game with me",
    "let's play something",
])
def test_en_play_conversation_is_not_media(text):
    assert _type(text, "en") != "MEDIA"


@pytest.mark.parametrize("text", [
    "play the music",
    "pause",
    "stop the music",
    "resume",
])
def test_en_media_with_context(text):
    assert _type(text, "en") == "MEDIA"


@pytest.mark.parametrize("text,kind", [
    ("sesi aç", "volume_up"),
    ("sesi kıs", "volume_down"),
    ("sustur", "volume_mute"),
    ("müziği duraklat", "play_pause"),
])
def test_tr_media(text, kind):
    r = route(text)
    assert r and r["type"] == "MEDIA" and r["payload"] == kind


# --- Memory: "don't forget X" is REMEMBER, not FORGET (regression) -----------

def test_en_dont_forget_is_remember():
    assert _type("don't forget to buy milk", "en") == "REMEMBER"


def test_en_forget_is_forget():
    assert _type("forget my coffee preference", "en") == "FORGET"


def test_en_remember():
    r = route("remember I like tea", "en")
    assert r["type"] == "REMEMBER" and "tea" in r["payload"]


def test_tr_remember():
    r = route("şunu hatırla kahveyi severim")
    assert r["type"] == "REMEMBER" and "kahve" in r["payload"]


def test_tr_forget():
    r = route("kahve tercihimi unut")
    assert r["type"] == "FORGET"


def test_tr_forget_all():
    r = route("her şeyi unut")
    assert r["type"] == "FORGET" and r["payload"] == "hepsi"


# --- App open with Turkish suffixes -----------------------------------------

@pytest.mark.parametrize("text,app", [
    ("not defteri aç", "not defteri"),
    ("hesap makinesini aç", "hesap makinesi"),
    ("chrome'u aç", "chrome"),
])
def test_tr_open_app(text, app):
    r = route(text)
    assert r and r["type"] == "APP" and r["payload"] == app


# --- YouTube ----------------------------------------------------------------

def test_tr_youtube():
    r = route("youtube'da tarkan aç")
    assert r and r["type"] == "YOUTUBE" and "tarkan" in r["payload"]


def test_en_youtube():
    r = route("play daft punk on youtube", "en")
    assert r and r["type"] == "YOUTUBE" and "daft punk" in r["payload"]


# --- Farewell ---------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
    ("görüşürüz", "tr"),
    ("hoşça kal", "tr"),
    ("go to sleep", "en"),
    ("stop listening", "en"),
])
def test_sleep(text, lang):
    assert _type(text, lang) == "SLEEP"


# --- Targeted click must NOT route (needs vision we don't have) --------------

@pytest.mark.parametrize("text,lang", [
    ("şu videoya tıkla", "tr"),
    ("click that video", "en"),
])
def test_targeted_click_defers(text, lang):
    # A bare click routes to MOUSE; a *targeted* one should defer to the LLM.
    assert _type(text, lang) != "MOUSE"


@pytest.mark.parametrize("text,lang", [
    ("tıkla", "tr"),
    ("click", "en"),
])
def test_bare_click_routes(text, lang):
    r = route(text, lang)
    assert r and r["type"] == "MOUSE" and r["payload"] == "click"


# --- Plain conversation defers to the LLM -----------------------------------

@pytest.mark.parametrize("text,lang", [
    ("bugün nasılsın", "tr"),
    ("what's the weather like", "en"),
    ("tell me a joke", "en"),
])
def test_conversation_defers(text, lang):
    assert route(text, lang) is None
