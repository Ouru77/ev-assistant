"""
E.V. — Voice AI Server
FastAPI backend: local Whisper STT, a local (Ollama) or Claude brain,
ElevenLabs/browser TTS, deterministic PC control, and long-term memory.

Author: Ouru77 — https://github.com/Ouru77/ev-assistant
License: MIT
"""

import asyncio
import base64
import json
import os
import re
import time

import anthropic
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

LLM_PROVIDER = config.get("llm_provider", "anthropic").lower()
OLLAMA_URL = config.get("ollama_url", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = config.get("ollama_model", "qwen2.5:7b")
TTS_PROVIDER = config.get("tts_provider", "elevenlabs").lower()
STT_PROVIDER = config.get("stt_provider", "browser").lower()
WHISPER_MODEL = config.get("whisper_model", "small")
WHISPER_DIR = config.get("whisper_dir", "")

ANTHROPIC_API_KEY = config.get("anthropic_api_key", "")
ELEVENLABS_API_KEY = config.get("elevenlabs_api_key", "")
ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")
USER_NAME = config.get("user_name", "dostum")
USER_ADDRESS = config.get("user_address", "dostum")
CITY = config.get("city", "İstanbul")
LANGUAGE = config.get("language", "tr").lower()
TASKS_FILE = config.get("obsidian_inbox_path", "")
PC_CONTROL = bool(config.get("pc_control", True))
CONVERSATION_MODE = bool(config.get("conversation_mode", True))
HISTORY_TURNS = int(config.get("history_turns", 30))  # how many recent messages to keep in context
NUM_CTX = int(config.get("num_ctx", 4096))            # Ollama context window; falls back if VRAM is tight

# --- Long-term memory: short facts E.V. remembers about the user ------------
MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")


def load_memories() -> list:
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("facts", [])
    except Exception:
        return []


def save_memories(facts: list):
    try:
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump({"facts": facts}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[E.V.] Hafıza yazılamadı: {e}", flush=True)


def add_memory(fact: str) -> str:
    fact = (fact or "").strip().rstrip(".")
    if not fact:
        return ""
    facts = load_memories()
    if any(fact.lower() == f.lower() for f in facts):
        return fact
    facts.append(fact)
    save_memories(facts[-50:])  # cap so the prompt stays small
    return fact


def forget_memory(query: str) -> bool:
    query = (query or "").strip().lower()
    facts = load_memories()
    if query in ("hepsi", "her şey", "hepsini", "all"):
        save_memories([])
        return True
    kept = [f for f in facts if query not in f.lower()]
    if len(kept) != len(facts):
        save_memories(kept)
        return True
    return False


MEMORIES = load_memories()

# Anthropic client is optional — only created if a real key is present.
ai = None
if ANTHROPIC_API_KEY and "YAPISTIR" not in ANTHROPIC_API_KEY:
    try:
        ai = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as e:
        print(f"[E.V.] Anthropic istemcisi kurulamadı: {e}", flush=True)

# Longer timeout — a local Ollama model on CPU can be slow to respond.
http = httpx.AsyncClient(timeout=180)


async def llm_chat(system: str, messages: list, max_tokens: int = 400) -> str:
    """Send a chat request to the configured LLM backend and return the reply text."""
    if LLM_PROVIDER == "ollama":
        msgs = [{"role": "system", "content": system}] + messages
        last_err = None
        # Try the configured context; if VRAM is tight (e.g. a game is running),
        # fall back to Ollama's default so E.V. still answers instead of erroring.
        for ctx in (NUM_CTX, None):
            opts = {"num_predict": max_tokens, "temperature": 0.7}
            if ctx:
                opts["num_ctx"] = ctx
            payload = {"model": OLLAMA_MODEL, "messages": msgs, "stream": False,
                       "keep_alive": "30m", "options": opts}
            try:
                resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
            except Exception as e:
                last_err = e
                print(f"[E.V.] llm_chat ctx={ctx} hatası, düşülüyor: {str(e)[:100]}", flush=True)
        raise last_err

    # Default: Anthropic
    if ai is None:
        return S("no_anthropic")
    response = await ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text


async def llm_stream(system: str, messages: list, max_tokens: int = 400):
    """Yield incremental text chunks from the LLM (Ollama streaming)."""
    if LLM_PROVIDER != "ollama":
        # No token streaming for Anthropic here — emit the whole reply as one chunk.
        yield await llm_chat(system, messages, max_tokens)
        return
    msgs = [{"role": "system", "content": system}] + messages
    last_err = None
    # Try the configured context; fall back to Ollama's default if VRAM is tight.
    for ctx in (NUM_CTX, None):
        opts = {"num_predict": max_tokens, "temperature": 0.7}
        if ctx:
            opts["num_ctx"] = ctx
        payload = {"model": OLLAMA_MODEL, "messages": msgs, "stream": True,
                   "keep_alive": "30m", "options": opts}
        yielded = False
        try:
            async with http.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    piece = obj.get("message", {}).get("content", "")
                    if piece:
                        yielded = True
                        yield piece
                    if obj.get("done"):
                        break
            return
        except Exception as e:
            last_err = e
            print(f"[E.V.] llm_stream ctx={ctx} hatası, düşülüyor: {str(e)[:100]}", flush=True)
            if yielded:
                raise  # already streamed part of the reply — don't restart it
    if last_err:
        raise last_err

app = FastAPI()

import browser_tools
import screen_capture
import whisper_stt
import pc_control
import command_router
import strings

pc_control.set_language(LANGUAGE)


def S(key, **kw):
    """Shorthand for a localized short string with USER_ADDRESS as default name."""
    kw.setdefault("name", USER_ADDRESS)
    return strings.s(key, LANGUAGE, **kw)

if STT_PROVIDER == "whisper":
    whisper_stt.configure(WHISPER_MODEL, WHISPER_DIR or None, LANGUAGE)


WMO_TR = {
    0: "açık", 1: "az bulutlu", 2: "parçalı bulutlu", 3: "çok bulutlu",
    45: "sisli", 48: "kırağılı sis", 51: "hafif çisenti", 53: "çisenti", 55: "yoğun çisenti",
    61: "hafif yağmur", 63: "yağmurlu", 65: "kuvvetli yağmur",
    71: "hafif kar", 73: "karlı", 75: "yoğun kar", 77: "kar taneleri",
    80: "sağanak", 81: "sağanak yağış", 82: "şiddetli sağanak",
    95: "gök gürültülü fırtına", 96: "dolulu fırtına", 99: "şiddetli dolulu fırtına",
}

WMO_EN = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "showers", 81: "rain showers", 82: "heavy showers",
    95: "thunderstorm", 96: "hail storm", 99: "severe hail storm",
}


def get_weather_sync():
    """Fetch current weather for CITY via open-meteo (free, reliable, no key)."""
    import urllib.request
    import urllib.parse
    try:
        q = urllib.parse.quote(CITY)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=tr"
        geo = json.loads(urllib.request.urlopen(geo_url, timeout=6).read())
        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
        )
        c = json.loads(urllib.request.urlopen(url, timeout=6).read())["current"]
        wmo = WMO_EN if LANGUAGE == "en" else WMO_TR
        return {
            "temp": round(c["temperature_2m"]),
            "feels_like": round(c["apparent_temperature"]),
            "description": wmo.get(c["weather_code"], "—"),
            "humidity": c["relative_humidity_2m"],
            "wind_kmh": round(c["wind_speed_10m"]),
        }
    except Exception:
        return None


def get_tasks_sync():
    """Read open tasks from Obsidian (sync)."""
    if not TASKS_FILE:
        return []
    try:
        tasks_path = os.path.join(TASKS_FILE, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip() for l in lines if l.strip().startswith("- [ ]")]
    except:
        return []


def refresh_data():
    """Refresh weather and tasks."""
    global WEATHER_INFO, TASKS_INFO
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO = get_tasks_sync()
    print(f"[E.V.] Hava: {WEATHER_INFO}", flush=True)
    print(f"[E.V.] Görevler: {len(TASKS_INFO)} yüklendi", flush=True)

WEATHER_INFO = ""
TASKS_INFO = []
refresh_data()

# Action parsing
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)

conversations: dict[str, list] = {}
pending_actions: dict[str, dict] = {}  # destructive actions awaiting a spoken "evet"
clients: set = set()  # connected WebSocket clients (for broadcast, e.g. fullscreen)

def build_system_prompt():
    wb = strings.weather_block(LANGUAGE, CITY, WEATHER_INFO) if WEATHER_INFO else ""
    tb = strings.task_block(LANGUAGE, TASKS_INFO) if TASKS_INFO else ""
    mb = strings.memory_block(LANGUAGE, USER_NAME, MEMORIES) if MEMORIES else ""
    pb = strings.pc_block(LANGUAGE) if PC_CONTROL else ""
    return strings.system_prompt(LANGUAGE, USER_NAME, USER_ADDRESS, CITY, wb, tb, mb, pb)


def greeting_prefix():
    return strings.greeting_prefix(LANGUAGE, time.localtime().tm_hour)


def build_greeting():
    """Deterministic, clean greeting spoken on session start."""
    parts = [f"{greeting_prefix()} {USER_NAME}."]
    if WEATHER_INFO:
        w = WEATHER_INFO
        parts.append(strings.s("weather_line", LANGUAGE, city=CITY, temp=w["temp"],
                               desc=w["description"].lower()))
    parts.append(strings.s("greet_ready", LANGUAGE))
    return " ".join(parts)


def get_system_prompt():
    return (
        build_system_prompt()
        .replace("{time}", time.strftime("%H:%M"))
        .replace("{greeting}", greeting_prefix())
    )


def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None


async def synthesize_speech(text: str) -> bytes:
    if not text.strip():
        return b""

    # Browser TTS: the frontend speaks the text via the Web Speech API — no audio
    # is generated server-side, so return empty and let the client handle it.
    if TTS_PROVIDER == "browser":
        return b""

    # Say the name "E.V." naturally: "İvi" (ee-vee) in Turkish, "Evie" in English.
    text = re.sub(r"E\.V\.?", "İvi" if LANGUAGE != "en" else "Evie", text)

    # Split long text into chunks at sentence boundaries to avoid ElevenLabs cutoff
    chunks = []
    if len(text) > 250:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current = ""
        for s in sentences:
            if len(current) + len(s) > 250 and current:
                chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip()
        if current:
            chunks.append(current.strip())
    else:
        chunks = [text]

    audio_parts = []
    for chunk in chunks:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        try:
            resp = await http.post(url, headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }, json={
                "text": chunk,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
            })
            print(f"  TTS chunk status: {resp.status_code}, size: {len(resp.content)}", flush=True)
            if resp.status_code == 200:
                audio_parts.append(resp.content)
            else:
                print(f"  TTS error body: {resp.text[:200]}", flush=True)
        except Exception as e:
            print(f"  TTS EXCEPTION: {e}", flush=True)

    return b"".join(audio_parts)


async def execute_action(action: dict) -> str:
    t = action["type"]
    p = action["payload"]

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return f"Sayfa: {result.get('title', '')}\nURL: {result.get('url', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Arama başarısız: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Sayfa: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Sayfaya ulaşılamadı: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Açıldı: {p}"

    elif t == "SCREEN":
        if ai is not None:
            return await screen_capture.describe_screen(ai)
        return S("no_screen")

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    elif t == "REMEMBER":
        saved = add_memory(p)
        global MEMORIES
        MEMORIES = load_memories()
        return f"__SPOKEN__{S('mem_saved')}" if saved else ""

    elif t == "FORGET":
        ok = forget_memory(p)
        MEMORIES = load_memories()
        return "__SPOKEN__" + (S("mem_forgot") if ok else S("mem_none"))

    elif t == "APP":
        return "__SPOKEN__" + await asyncio.to_thread(pc_control.open_app, p)

    elif t == "MEDIA":
        return "__SPOKEN__" + await asyncio.to_thread(pc_control.media, p)

    elif t == "CLOSE":
        return "__SPOKEN__" + await asyncio.to_thread(pc_control.close_app, p)

    elif t == "POWER":
        return "__SPOKEN__" + await asyncio.to_thread(pc_control.power, p)

    elif t == "CMD":
        return await asyncio.to_thread(pc_control.run_command, p)

    elif t == "MOUSE":
        return "__SPOKEN__" + await asyncio.to_thread(pc_control.mouse, p)

    elif t == "YOUTUBE":
        res = await browser_tools.youtube_open(p)
        if "error" in res:
            return f"__SPOKEN__{S('action_failed')}"
        if LANGUAGE == "en":
            return f"__SPOKEN__Opening {p} on YouTube."
        return f"__SPOKEN__YouTube'da {p} açılıyor."

    return ""


# Actions that change the machine → require a spoken yes before running.
DESTRUCTIVE_ACTIONS = {"CLOSE", "POWER", "CMD"}


def confirm_prompt(action: dict) -> str:
    """A short yes/no question E.V. asks before a destructive action."""
    t, p = action["type"], action["payload"]
    if t == "CLOSE":
        return S("confirm_close", app=p)
    if t == "POWER":
        verb = strings.power_confirm(p, LANGUAGE)
        return f"{verb}, {USER_ADDRESS}?" if LANGUAGE == "en" else f"{verb} mı, {USER_ADDRESS}?"
    if t == "CMD":
        return S("confirm_cmd", cmd=p)
    return S("confirm_generic")


async def _warm_ollama():
    """Load the model into VRAM at startup so the user's first reply isn't cold."""
    if LLM_PROVIDER != "ollama":
        return
    try:
        await http.post(f"{OLLAMA_URL}/api/chat", json={
            "model": OLLAMA_MODEL, "stream": False, "keep_alive": "30m",
            "messages": [{"role": "user", "content": "merhaba"}],
            "options": {"num_predict": 1, "num_ctx": NUM_CTX},  # match real requests → no reload
        }, timeout=180)
        print("[E.V.] Model ısıtıldı (VRAM).", flush=True)
    except Exception as e:
        print(f"[E.V.] Isıtma hatası: {e}", flush=True)


async def _fullscreen_watch():
    """Poll for a fullscreen app and tell clients to tray/restore E.V. accordingly."""
    last = None
    while True:
        try:
            active = await asyncio.to_thread(pc_control.fullscreen_active)
            if active != last:
                last = active
                dead = []
                for ws in list(clients):
                    try:
                        await ws.send_json({"type": "fullscreen", "active": active})
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    clients.discard(ws)
        except Exception as e:
            print(f"[E.V.] Tam ekran izleme hatası: {e}", flush=True)
        await asyncio.sleep(1.5)


@app.on_event("startup")
async def _on_startup():
    asyncio.create_task(_warm_ollama())
    asyncio.create_task(_fullscreen_watch())


async def speak_chunk(text: str, ws: WebSocket):
    """Synthesize + stream one spoken sentence to the client as a response chunk."""
    text = (text or "").strip()
    if not text:
        return
    audio = await synthesize_speech(text)
    print(f"  E.V. »: {text[:60]}", flush=True)
    await ws.send_json({
        "type": "response_chunk",
        "text": text,
        "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
    })


_YES = {"evet", "olur", "tamam", "yap", "tabii", "tabi", "aynen", "onayla",
        "kesinlikle", "elbette", "yapabilirsin", "devam", "hı hı", "hıhı",
        "yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "do it"}
_NO = {"hayır", "hayir", "yok", "dur", "vazgeç", "vazgec", "iptal", "istemiyorum",
       "gerek yok", "boşver", "bosver", "olmaz",
       "no", "nope", "don't", "dont", "cancel", "stop", "never mind", "nevermind"}


def _matches(text: str, words: set) -> bool:
    t = " " + re.sub(r"[^\wçğıöşü ]", " ", (text or "").lower()) + " "
    return any(f" {w} " in t for w in words)


async def _speak_response(session_id: str, text: str, ws: WebSocket):
    audio = await synthesize_speech(text)
    conversations.setdefault(session_id, []).append({"role": "assistant", "content": text})
    await ws.send_json({
        "type": "response", "text": text,
        "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
    })


async def process_message(session_id: str, user_text: str, ws: WebSocket):
    """Process message and send responses via WebSocket."""
    if session_id not in conversations:
        conversations[session_id] = []

    # If a destructive action is awaiting confirmation, read this reply as yes/no.
    if session_id in pending_actions:
        if _matches(user_text, _YES):
            action = pending_actions.pop(session_id)
            await deliver_action(session_id, action, ws)
            return
        if _matches(user_text, _NO):
            pending_actions.pop(session_id, None)
            await _speak_response(session_id, S("canceled"), ws)
            return
        pending_actions.pop(session_id, None)  # unrelated reply → drop the pending action

    # Refresh weather + tasks on greeting/activation
    lower_text = user_text.lower()
    is_greeting = any(w in lower_text for w in
                      ("selam", "aktif", "activate", "hello", "hi ", "hey", "merhaba"))
    if is_greeting:
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})

    # First activation of a fresh session → deterministic clean greeting (no LLM).
    if len(conversations[session_id]) == 1 and is_greeting:
        greeting = build_greeting()
        audio = await synthesize_speech(greeting)
        conversations[session_id].append({"role": "assistant", "content": greeting})
        print(f"  E.V. (selam): {greeting}", flush=True)
        await ws.send_json({
            "type": "response",
            "text": greeting,
            "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
        })
        return

    # Deterministic PC / memory command routing — runs BEFORE the LLM so explicit
    # commands work reliably even when a small local model won't emit action tags.
    # Memory (REMEMBER/FORGET) always routes; PC actions only when pc_control is on.
    routed = command_router.route(user_text, LANGUAGE)
    if routed and (PC_CONTROL or routed["type"] in ("REMEMBER", "FORGET")):
        print(f"  Routed: {routed['type']} -> {routed['payload'][:80]}", flush=True)
        if routed["type"] in DESTRUCTIVE_ACTIONS:
            pending_actions[session_id] = routed
            question = confirm_prompt(routed)
            audio = await synthesize_speech(question)
            await ws.send_json({
                "type": "confirm", "text": question,
                "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
            })
            return
        await deliver_action(session_id, routed, ws)
        return

    history = conversations[session_id][-HISTORY_TURNS:]

    if TTS_PROVIDER == "browser":
        # Browser speech reads the whole reply — streaming brings no benefit.
        full = await llm_chat(get_system_prompt(), history, max_tokens=400)
        spoken_text, action = extract_action(full)
        if spoken_text:
            conversations[session_id].append({"role": "assistant", "content": spoken_text})
            await ws.send_json({"type": "response", "text": spoken_text, "audio": ""})
    else:
        # Stream the reply and speak sentence-by-sentence for lower latency.
        full, buf, stop_speaking = "", "", False
        try:
            async for piece in llm_stream(get_system_prompt(), history, 400):
                full += piece
                if stop_speaking:
                    continue
                buf += piece
                if "[ACTION" in buf:  # action tag begins — speak text before it, then stop
                    await speak_chunk(buf[:buf.find("[ACTION")], ws)
                    buf, stop_speaking = "", True
                    continue
                segs = re.split(r'(?<=[.!?…])\s+', buf)  # flush completed sentences
                if len(segs) > 1:
                    for seg in segs[:-1]:
                        await speak_chunk(seg, ws)
                    buf = segs[-1]
        except Exception as e:
            print(f"  Stream hatası: {e}", flush=True)
        if not stop_speaking:
            await speak_chunk(buf, ws)
        spoken_text, action = extract_action(full)
        if spoken_text:
            conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await ws.send_json({"type": "response_done"})

    print(f"  LLM raw: {full[:200]}", flush=True)

    # Execute action if any
    if action:
        print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

        # Destructive actions (close app / power / shell) → ask first, run on "evet".
        if action["type"] in DESTRUCTIVE_ACTIONS:
            pending_actions[session_id] = action
            question = confirm_prompt(action)
            audio = await synthesize_speech(question)
            await ws.send_json({
                "type": "confirm",
                "text": question,
                "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
            })
            return

        await deliver_action(session_id, action, ws)


async def deliver_action(session_id: str, action: dict, ws: WebSocket):
    """Run a (already-approved / non-destructive) action and speak the result."""
    # Quick voice feedback for SCREEN so the user knows E.V. is working.
    if action["type"] == "SCREEN":
        hint = S("screen_hint")
        hint_audio = await synthesize_speech(hint)
        await ws.send_json({
            "type": "response",
            "text": hint,
            "audio": base64.b64encode(hint_audio).decode("utf-8") if hint_audio else "",
        })

    try:
        action_result = await execute_action(action)
        print(f"  Result: {str(action_result)[:200]}", flush=True)
    except Exception as e:
        print(f"  Action error: {e}", flush=True)
        action_result = f"__SPOKEN__{S('action_problem')}"

    if action["type"] == "OPEN":
        return  # just opened a browser tab, nothing to summarize

    if not action_result:
        return  # silent action (e.g. duplicate memory)

    # __SPOKEN__ prefix → speak the line verbatim, don't summarize (PC/memory acks).
    if isinstance(action_result, str) and action_result.startswith("__SPOKEN__"):
        summary = action_result[len("__SPOKEN__"):].strip()
    elif "başarısız" not in action_result and "ulaşılamadı" not in action_result:
        if LANGUAGE == "en":
            sys_sum = (f"You are E.V. Summarize the info below briefly in English, at most 3 "
                       f"sentences, calm and plain E.V. style. Address the user by name as "
                       f"'{USER_ADDRESS}'. NO brackets/tags. NO ACTION tag.")
            user_sum = f"Summarize this:\n\n{action_result}"
        else:
            sys_sum = (f"Sen E.V.'sin. Aşağıdaki bilgileri KISA şekilde Türkçe özetle, en fazla 3 "
                       f"cümle, sakin ve sade E.V. tarzında. Kullanıcıya '{USER_ADDRESS}' diye "
                       f"ismiyle hitap et. Köşeli parantez içinde etiket YOK. ACTION etiketi YOK.")
            user_sum = f"Şunu özetle:\n\n{action_result}"
        summary = await llm_chat(sys_sum, [{"role": "user", "content": user_sum}], max_tokens=250)
        summary, _ = extract_action(summary)
    else:
        summary = S("action_failed")

    audio2 = await synthesize_speech(summary)
    conversations[session_id].append({"role": "assistant", "content": summary})
    await ws.send_json({
        "type": "response",
        "text": summary,
        "audio": base64.b64encode(audio2).decode("utf-8") if audio2 else "",
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(id(ws))
    clients.add(ws)
    print(f"[E.V.] İstemci bağlandı", flush=True)

    try:
        while True:
            data = await ws.receive_json()
            # Any failure while handling ONE message must not drop the connection.
            try:
                # Confirmation reply for a pending destructive action.
                if "confirm" in data:
                    pending = pending_actions.pop(session_id, None)
                    if data.get("confirm") and pending:
                        await deliver_action(session_id, pending, ws)
                    else:
                        cancel = f"Tamam {USER_ADDRESS}, vazgeçtim."
                        caudio = await synthesize_speech(cancel)
                        await ws.send_json({
                            "type": "response", "text": cancel,
                            "audio": base64.b64encode(caudio).decode("utf-8") if caudio else "",
                        })
                    continue

                # Whisper STT path: client recorded audio and sent it as base64.
                if data.get("audio"):
                    try:
                        audio_bytes = base64.b64decode(data["audio"])
                        user_text = await asyncio.to_thread(whisper_stt.transcribe, audio_bytes)
                    except Exception as e:
                        print(f"  STT hata: {e}", flush=True)
                        await ws.send_json({"type": "idle"})
                        continue
                    user_text = (user_text or "").strip()
                    if not user_text:
                        await ws.send_json({"type": "idle"})  # nothing understood
                        continue
                    await ws.send_json({"type": "user_text", "text": user_text})
                    print(f"  You(whisper): {user_text}", flush=True)
                    await process_message(session_id, user_text, ws)
                    continue

                # Text path: greeting on connect, or plain text messages.
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue
                print(f"  You:    {user_text}", flush=True)
                await process_message(session_id, user_text, ws)

            except WebSocketDisconnect:
                raise
            except Exception as e:
                # LLM/TTS/tool error — stay connected, tell the user gracefully.
                print(f"  İşlem hatası: {type(e).__name__}: {e}", flush=True)
                try:
                    await ws.send_json({
                        "type": "response",
                        "text": S("glitch"),
                        "audio": "",
                    })
                except Exception:
                    pass

    except WebSocketDisconnect:
        conversations.pop(session_id, None)
        pending_actions.pop(session_id, None)
    finally:
        clients.discard(ws)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


_GPU_NAME = None


def get_gpu_name() -> str:
    """Detect the primary GPU once (Windows), cached. Falls back to 'GPU'."""
    global _GPU_NAME
    if _GPU_NAME is not None:
        return _GPU_NAME
    name = "GPU"
    try:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending "
             "| Select-Object -First 1).Name"],
            capture_output=True, text=True, timeout=8,
        )
        n = (r.stdout or "").strip()
        if n:
            name = n.replace("AMD ", "").replace("NVIDIA ", "").replace("(R)", "").strip()
    except Exception:
        pass
    _GPU_NAME = name
    return name


def module_info():
    """What each subsystem is on THIS machine (so every user sees their own)."""
    brain = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else "claude"
    return {
        "stt": STT_PROVIDER,
        "brain": brain,
        "voice": TTS_PROVIDER,
        "gpu": get_gpu_name(),
    }


@app.get("/stats")
async def stats():
    import psutil
    vm = psutil.virtual_memory()
    app_drive = os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep
    try:
        disk = psutil.disk_usage(app_drive)
    except Exception:
        disk = psutil.disk_usage(os.sep)
    return {
        "cpu": round(psutil.cpu_percent(interval=None)),
        "ram": round(vm.percent),
        "ram_used_gb": round(vm.used / 1e9, 1),
        "ram_total_gb": round(vm.total / 1e9, 1),
        "disk": round(disk.percent),
        "disk_free_gb": round(disk.free / 1e9, 0),
        "disk_drive": app_drive.rstrip("\\/"),
        "weather": WEATHER_INFO or None,
        "city": CITY,
        "language": LANGUAGE,
        "modules": module_info(),
    }


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(os.path.dirname(__file__), "electron", "icon.png"))


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  E.V. — Voice AI Server  ·  by Ouru77", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("  github.com/Ouru77/ev-assistant", flush=True)
    print("=" * 50, flush=True)
    # Bind to loopback only → the assistant is reachable from THIS machine alone,
    # never from other devices on the network. (Electron/browser use localhost.)
    uvicorn.run(app, host="127.0.0.1", port=8340)
