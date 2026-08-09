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
    (r"\b(yeniden başlat|tekrar başlat|restart|resetle)", "yeniden başlat"),
    (r"\b(uyku(ya)?( moduna)?( al)?|uyut|uykuya geç)", "uyku"),
    (r"\b(ekranı kilitle|bilgisayarı kilitle|kilitle)", "kilitle"),
]

_MEM_TRIGGER = r"\b(hatırla|hatirla|aklında tut|aklinda tut|not al|not et|unutma)\b"
_FORGET_TRIGGER = r"\b(unut|unutabilirsin|sil bunu|hafızandan sil)\b"

# ---- English rule sets (used when lang == "en") ----------------------------
_MEDIA_RULES_EN = [
    (r"\b(mute|silence)\b", "volume_mute"),
    (r"\b(volume up|turn (it|the volume) up|louder|raise the volume|increase (the )?volume)\b", "volume_up"),
    (r"\b(volume down|turn (it|the volume) down|quieter|lower the volume|decrease (the )?volume)\b", "volume_down"),
    (r"\b(next|skip)\b.{0,10}\b(song|track|tune)|\bskip( this)?\b", "next"),
    (r"\b(previous|prev|last|go back)\b.{0,10}\b(song|track|tune)|\bgo back\b", "prev"),
    (r"\b(pause|resume|play|stop)\b", "play_pause"),
]
_POWER_RULES_EN = [
    (r"\bcancel (the )?(shutdown|shut down)\b", "iptal"),
    (r"\b(shut ?down|turn off)\b.{0,14}\b(computer|pc|system|machine)|\bshut ?down\b", "kapat"),
    (r"\b(restart|reboot|reset)\b", "yeniden başlat"),
    (r"\b(sleep|suspend|hibernate)\b", "uyku"),
    (r"\block( the)? (screen|computer|pc)|\block it\b|\block\b", "kilitle"),
]
_MEM_TRIGGER_EN = r"\b(remember|keep in mind|note that|don'?t forget|make a note)\b"
_FORGET_TRIGGER_EN = r"\b(forget|erase|delete this)\b"


def route(text: str, lang: str = "tr"):
    """Return an action dict for a clear command, or None to defer to the LLM."""
    if lang == "en":
        return _route_en(_norm(text))
    t = _norm(text)
    if not t:
        return None

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

    if re.search(_FORGET_TRIGGER_EN, t):
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
