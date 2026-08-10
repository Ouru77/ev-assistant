"""
E.V. — deterministic command router.

Small local LLMs (e.g. gemma2:9b) are unreliable at emitting [ACTION:...] tags
for PC commands — they tend to just *say* "opening it" without triggering
anything. So we catch clear, imperative Turkish commands here BEFORE the LLM and
turn them into action dicts directly. Conversational input returns None and
falls through to the model as usual.
"""

import re

from pc_control import APPS

# App names sorted longest-first so "görev yöneticisi" wins over "gezgin", etc.
_APP_NAMES = sorted(APPS.keys(), key=len, reverse=True)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _find_app(t: str):
    # Prefix match + \w* so Turkish suffixes attach ("defteri" → "defterini",
    # "makinesi" → "makinesini"). Apostrophes ("chrome'u") end the word anyway.
    for name in _APP_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\w*", t):
            return name
    return None


# Verb cues (kept loose; Turkish suffixes handled with word-prefix matching).
_OPEN = r"\b(aç|açar|açsana|açıver|başlat|çalıştır|getir)"
_CLOSE = r"\b(kapat|kapatır|kapatsana|sonlandır|öldür)"
_OPEN_EN = r"\b(open|launch|start|run|bring up)\b"
_CLOSE_EN = r"\b(close|quit|kill|exit|shut down)\b"

_MEDIA_RULES = [
    (r"\b(sustur|sessize al)\b|ses.{0,14}\b(kapat|kes)", "volume_mute"),
    (r"ses.{0,14}\b(aç|yükselt|artır|arttır|çoğalt|yükselt)", "volume_up"),
    (r"ses.{0,14}\b(kıs|azalt|düşür|indir|alçalt)", "volume_down"),
    (r"\b(sonraki|bir sonraki|diğer)\b.{0,10}\b(şarkı|parça|müzik)|\bşarkıyı geç|\bgeç bunu", "next"),
    (r"\b(önceki|bir önceki|geri)\b.{0,10}\b(şarkı|parça|müzik)|\bbaşa (al|sar)", "prev"),
    (r"\b(duraklat|durdur)\b|\bmüziği (durdur|duraklat)", "play_pause"),
    (r"\b(oynat|çal|devam et)\b.{0,14}\b(şarkı|müzik|parça)|\bmüziği (oynat|çal|başlat)|\bmüzik aç", "play_pause"),
]

_POWER_RULES = [
    (r"\b(kapatmayı iptal|iptal et|vazgeç kapat|kapatma)", "iptal"),
    (r"\b(bilgisayarı|pc('?y[ıi])?|sistemi|makineyi|makinayı) (kapat|kapatır)", "kapat"),
    # Restart needs an explicit PC context — otherwise "spotify'ı yeniden başlat"
    # would reboot the machine instead of the app.
    (r"\b(bilgisayar|pc|sistem|makine|makina)\w*.{0,8}(yeniden başlat|tekrar başlat|resetle|restart)", "yeniden başlat"),
    (r"\b(uyku(ya)?( moduna)?( al)?|uyut|uykuya geç)", "uyku"),
    (r"\b(ekranı kilitle|bilgisayarı kilitle|kilitle)", "kilitle"),
]

_MEM_TRIGGER = r"\b(hatırla|hatirla|aklında tut|aklinda tut|not al|not et|unutma)\b"
_FORGET_TRIGGER = r"\b(unut|unutabilirsin|sil bunu|hafızandan sil)\b"

_MOUSE_RULES = [
    (r"\bsağ (tıkla|tık|klik)", "right"),
    (r"\bçift tıkla", "double"),
    (r"\b(tıkla|tıklar mısın|klik yap)\b", "click"),
    (r"\b(aşağı|aşşağı) (kaydır|in)\b", "scroll_down"),
    (r"\b(yukarı|yukari) (kaydır|çık)\b", "scroll_up"),
]
_MOUSE_RULES_EN = [
    (r"\bright[- ]?click", "right"),
    (r"\bdouble[- ]?click", "double"),
    (r"\bclick\b", "click"),
    (r"\bscroll down\b", "scroll_down"),
    (r"\bscroll up\b", "scroll_up"),
]

# ---- English rule sets (used when lang == "en") ----------------------------
_MEDIA_RULES_EN = [
    (r"\b(mute|silence)\b", "volume_mute"),
    (r"\b(volume up|turn (it|the volume) up|louder|raise the volume|increase (the )?volume)\b", "volume_up"),
    (r"\b(volume down|turn (it|the volume) down|quieter|lower the volume|decrease (the )?volume)\b", "volume_down"),
    (r"\b(next|skip)\b.{0,10}\b(song|track|tune)|\bskip( this)?\b", "next"),
    (r"\b(previous|prev|last|go back)\b.{0,10}\b(song|track|tune)|\bgo back\b", "prev"),
    # pause/resume are almost always media; bare play/stop are not ("play a game"),
    # so those need a music/playback context to fire.
    (r"\b(pause|resume)\b|\b(play|stop|start)\s+(the\s+)?(music|song|track|playback|it)\b|\b(music|song|track|playback)\b.{0,12}\b(play|stop|pause|resume)\b", "play_pause"),
]
_POWER_RULES_EN = [
    (r"\bcancel (the )?(shutdown|shut down)\b", "iptal"),
    (r"\b(shut ?down|turn off)\b.{0,14}\b(computer|pc|system|machine)|\bshut ?down\b", "kapat"),
    # "restart spotify" must not reboot the PC — restart/reset need a PC context.
    # (reboot on its own is unambiguous, so it stays bare.)
    (r"\b(restart|reset)\b.{0,14}\b(computer|pc|system|machine)|\b(computer|pc|system|machine)\b.{0,14}\b(restart|reboot|reset)\b|\breboot\b", "yeniden başlat"),
    (r"\b(sleep|suspend|hibernate)\b", "uyku"),
    (r"\block( the)? (screen|computer|pc)|\block it\b|\block\b", "kilitle"),
]
_MEM_TRIGGER_EN = r"\b(remember|keep in mind|note that|don'?t forget|make a note)\b"
_FORGET_TRIGGER_EN = r"\b(forget|erase|delete this)\b"

_BYE_TR = r"\b(görüşürüz|görüşmek üzere|hoşça ?kal|hoşca ?kal|güle güle|kendine iyi bak|bay ?bay|kapan(abilirsin)?|kendini kapat|uyu(yabilirsin)?|dinlemeyi (bırak|kapat)|sessize geç)\b"
_BYE_EN = r"\b(goodbye|good bye|see you|see ya|bye( now)?|take care|go to sleep|sleep now|stop listening|mute yourself)\b"


def route(text: str, lang: str = "tr"):
    """Return an action dict for a clear command, or None to defer to the LLM."""
    if lang == "en":
        return _route_en(_norm(text))
    t = _norm(text)
    if not t:
        return None

    # --- Farewell → go to sleep (stop listening) ---
    if re.search(_BYE_TR, t):
        return {"type": "SLEEP", "payload": ""}

    # --- Memory: forget ---
    if re.search(_FORGET_TRIGGER, t):
        if re.search(r"\b(hepsi\w*|her ?şey\w*|tüm\w*)\b", t):
            return {"type": "FORGET", "payload": "hepsi"}
        after = re.sub(r".*?\b(unut(abilirsin)?|sil bunu|hafızandan sil)\b", "", t).strip(" :,.")
        before = re.split(_FORGET_TRIGGER, t)[0].strip(" :,.")  # "kahve tercihimi unut"
        q = after or before
        if q:
            return {"type": "FORGET", "payload": q}

    # --- Memory: remember ---
    if re.search(_MEM_TRIGGER, t):
        m = re.search(r"\b(?:hatırla|hatirla|aklında tut|aklinda tut|not al|not et|unutma)\b[:,]?\s*(.+)", t)
        after = m.group(1).strip(" :,.") if m else ""
        before = re.split(_MEM_TRIGGER, t)[0]
        before = re.sub(r"\b(bunu|şunu|sunu|lütfen|lutfen)\b", "", before).strip(" :,.")
        fact = after or before
        if fact and len(fact) > 2:
            return {"type": "REMEMBER", "payload": fact}

    # --- YouTube by name ("youtube'da X aç/çal") ---
    if "youtube" in t and re.search(r"\b(aç|açsana|çal|oynat|başlat|dinle)\b", t):
        q = re.sub(r"\byoutube\w*\b", " ", t)
        q = re.sub(r"\b(aç|açsana|açar|mısın|çal|oynat|başlat|dinle|göster|bana|lütfen|bir|şu|bu|videoyu|şarkıyı|şarkı|video)\b", " ", q)
        q = re.sub(r"['’]\w*", "", q)
        q = re.sub(r"\s+", " ", q).strip(" ,.'")
        if q:
            return {"type": "YOUTUBE", "payload": q}

    # --- Mouse (clicks / scroll at current cursor) ---
    # A *targeted* click ("şu videoya tıkla", "şuna tıkla") means a specific
    # on-screen element → needs vision we don't have. Only bare clicks (at the
    # cursor) route here; targeted ones fall through so the LLM refuses honestly.
    targeted_click = re.search(
        r"\b\w+(ya|ye|na|ne)\s+(sağ\s+|sol\s+|çift\s+)?(tıkla|tık|klik)"
        r"|\b(şuna|buna|ona|oraya|buraya|şuraya)\b", t)
    for pat, kind in _MOUSE_RULES:
        if re.search(pat, t):
            if kind in ("click", "double", "right") and targeted_click:
                break  # targeted click → let the LLM say it can't
            return {"type": "MOUSE", "payload": kind}

    # --- Media / volume (check before app-open, since "sesi aç" holds "aç") ---
    for pat, kind in _MEDIA_RULES:
        if re.search(pat, t):
            return {"type": "MEDIA", "payload": kind}

    # --- Power (check before app-close, since it holds "kapat") ---
    for pat, kind in _POWER_RULES:
        if re.search(pat, t):
            return {"type": "POWER", "payload": kind}

    # --- App close (destructive) ---
    if re.search(_CLOSE, t):
        app = _find_app(t)
        if app:
            return {"type": "CLOSE", "payload": app}

    # --- App open ---
    if re.search(_OPEN, t):
        app = _find_app(t)
        if app:
            return {"type": "APP", "payload": app}

    return None


def _route_en(t: str):
    """English command routing."""
    if not t:
        return None

    if re.search(_BYE_EN, t):
        return {"type": "SLEEP", "payload": ""}

    # "don't forget X" is a REMEMBER, not a FORGET — guard the forget trigger so
    # the "forget" inside "don't forget" doesn't try to delete a memory.
    if re.search(_FORGET_TRIGGER_EN, t) and not re.search(r"don'?t\s+forget", t):
        if re.search(r"\b(everything|all|it all)\b", t):
            return {"type": "FORGET", "payload": "hepsi"}
        after = re.sub(r".*?\b(forget|erase|delete this)\b", "", t).strip(" :,.")
        if after:
            return {"type": "FORGET", "payload": after}

    if re.search(_MEM_TRIGGER_EN, t):
        m = re.search(r"\b(?:remember|keep in mind|note that|note|don'?t forget)\b(?:\s+that)?[:,]?\s*(.+)", t)
        fact = (m.group(1).strip(" :,.") if m else "")
        if fact and len(fact) > 2:
            return {"type": "REMEMBER", "payload": fact}

    if "youtube" in t and re.search(r"\b(play|open|put on|search)\b", t):
        q = re.sub(r"\byoutube\b", " ", t)
        q = re.sub(r"\b(play|open|put on|search|for|on|the|a|please|me|video|song)\b", " ", q)
        q = re.sub(r"\s+", " ", q).strip(" ,.")
        if q:
            return {"type": "YOUTUBE", "payload": q}

    targeted_click_en = re.search(r"\bclick\s+(on\s+)?(the|that|this|a|an)?\s*\w+", t)
    for pat, kind in _MOUSE_RULES_EN:
        if re.search(pat, t):
            if kind == "click" and targeted_click_en:
                break  # "click that video" → needs vision → let the LLM refuse
            return {"type": "MOUSE", "payload": kind}

    for pat, kind in _MEDIA_RULES_EN:
        if re.search(pat, t):
            return {"type": "MEDIA", "payload": kind}

    for pat, kind in _POWER_RULES_EN:
        if re.search(pat, t):
            return {"type": "POWER", "payload": kind}

    if re.search(_CLOSE_EN, t):
        app = _find_app(t)
        if app:
            return {"type": "CLOSE", "payload": app}

    if re.search(_OPEN_EN, t):
        app = _find_app(t)
        if app:
            return {"type": "APP", "payload": app}

    return None
