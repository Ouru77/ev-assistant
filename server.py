"""
E.V. — Voice AI Server
FastAPI backend: receives speech text, thinks with Claude Haiku,
speaks with ElevenLabs, controls browser with Playwright.
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
USER_NAME = config.get("user_name", "Oğul")
USER_ADDRESS = config.get("user_address", "Oğul")
CITY = config.get("city", "İstanbul")
TASKS_FILE = config.get("obsidian_inbox_path", "")

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
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": False,
            "keep_alive": "30m",  # keep the model warm in VRAM between turns
            "options": {"num_predict": max_tokens, "temperature": 0.7},
        }
        resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    # Default: Anthropic
    if ai is None:
        return "Anthropic anahtarı yok, Oğul. Ya bir anahtar gir ya da Ollama'ya geç."
    response = await ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text

app = FastAPI()

import browser_tools
import screen_capture
import whisper_stt

if STT_PROVIDER == "whisper":
    whisper_stt.configure(WHISPER_MODEL, WHISPER_DIR or None)


WMO_TR = {
    0: "açık", 1: "az bulutlu", 2: "parçalı bulutlu", 3: "çok bulutlu",
    45: "sisli", 48: "kırağılı sis", 51: "hafif çisenti", 53: "çisenti", 55: "yoğun çisenti",
    61: "hafif yağmur", 63: "yağmurlu", 65: "kuvvetli yağmur",
    71: "hafif kar", 73: "karlı", 75: "yoğun kar", 77: "kar taneleri",
    80: "sağanak", 81: "sağanak yağış", 82: "şiddetli sağanak",
    95: "gök gürültülü fırtına", 96: "dolulu fırtına", 99: "şiddetli dolulu fırtına",
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
        return {
            "temp": round(c["temperature_2m"]),
            "feels_like": round(c["apparent_temperature"]),
            "description": WMO_TR.get(c["weather_code"], "bilinmiyor"),
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

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\n{CITY} havası: {w['temp']}°C, hissedilen {w['feels_like']}°C, {w['description']}"

    task_block = ""
    if TASKS_INFO:
        task_block = f"\nAçık görevler ({len(TASKS_INFO)}): " + ", ".join(TASKS_INFO[:5])

    return f"""Sen E.V.'sin — {USER_NAME}'un kendi yaptığı yapay zeka asistanı. Onun atölyesindeki en yakın yardımcısısın. Sakin, zeki, mütevazı; gösterişsiz, DIY ruhlu bir dostsun. Telaşlanmaz, abartmazsın; sıcak ama sade konuşursun.

MUTLAK KURALLAR (bunları ihlal etme):
1. SADECE TÜRKÇE yaz. İngilizce, Çince, Arapça ya da başka hiçbir dilden tek kelime, tek harf kullanma. Türkçe alfabe dışında karakter (örn. Çince/Japonca harfler) KESİNLİKLE yasak.
2. Kullanıcıya HER ZAMAN senli-benli, "sen" diye hitap et. "-sın/-sin", "yaparsın", "ister misin" gibi. ASLA "siz", "-siniz", "yapabilirsiniz", "efendim", "beyefendi" kullanma. Ona ismiyle "{USER_ADDRESS}" diye seslen.
3. BİLGİ UYDURMA. Aşağıdaki "GÜNCEL VERİLER" bölümünde sana açıkça verilmeyen hiçbir şeyi (hava durumu, sıcaklık, görevler, tarih, haber) söyleme. Emin değilsen "bilmiyorum" de ya da o konuya hiç girme. Var olmayan hava durumu, derece vb. asla söyleme.
4. Cevapların KISA olsun — en fazla 2-3 cümle. Her yazdığın sesli okunacak.
5. Köşeli parantez içinde sahne yönergesi/etiket ([sakin] gibi) yazma. Tonun kelime seçiminden gelsin.

AKSİYONLAR: Kullanıcı SENDEN AÇIKÇA bir şey yapmanı isterse (bir şey aramak, bir site açmak, ekranına bakmak, haber getirmek), o zaman ilgili aksiyonu cevabının EN SONUNA yaz. Sıradan sohbette aksiyon KULLANMA — sadece cevap ver.
[ACTION:SEARCH] arama terimi — internette ara
[ACTION:OPEN] url — tarayıcıda site aç
[ACTION:SCREEN] — sadece "ekrana bak / ne görüyorsun" dendiğinde. O zaman SADECE bu satırı yaz, önüne hiç metin yazma.
[ACTION:NEWS] — sadece haber/gündem sorulduğunda. Önüne kısa bir cümle yaz.

Oturum yeni başladığında ya da "Selam E.V." dendiğinde: kısa, doğal bir Türkçe selam ver. Selama tam olarak "{{greeting}}" ile başla ve ona doğrudan seslen (örnek: "{{greeting}} Oğul, hazırım — bugün ne yapıyoruz?"). "İyi öğleden sonra" gibi çeviri kokan ifadeler ASLA kullanma. Ondan üçüncü şahıs gibi ("Oğul'a yardımcı") değil, ikinci şahıs olarak ("sana yardımcı") bahset. Aşağıda hava verisi VARSA tek cümleyle söyle; YOKSA havadan HİÇ bahsetme.

=== GÜNCEL VERİLER ==={weather_block if weather_block else " (şu an hava verisi yok — havadan bahsetme)"}{task_block if task_block else " (açık görev yok)"}
==="""


def turkish_greeting():
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return "Günaydın"
    if 11 <= h < 18:
        return "İyi günler"
    if 18 <= h < 22:
        return "İyi akşamlar"
    return "İyi geceler"


def build_greeting():
    """Deterministic, clean Turkish greeting spoken on session start."""
    parts = [f"{turkish_greeting()} {USER_NAME}."]
    if WEATHER_INFO:
        w = WEATHER_INFO
        parts.append(f"{CITY}'de hava {w['temp']} derece, {w['description'].lower()}.")
    parts.append("Hazırım, bugün ne yapıyoruz?")
    return " ".join(parts)


def get_system_prompt():
    return (
        build_system_prompt()
        .replace("{time}", time.strftime("%H:%M"))
        .replace("{greeting}", turkish_greeting())
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

    # Say the name "E.V." as "İvi" (ee-vee), not the Turkish word "ev".
    text = re.sub(r"E\.V\.?", "İvi", text)

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
        return "Şu an ekranı göremiyorum, Oğul — görme için ayrı bir görsel model gerekiyor, onu sonra ekleriz."

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    return ""


async def process_message(session_id: str, user_text: str, ws: WebSocket):
    """Process message and send responses via WebSocket."""
    if session_id not in conversations:
        conversations[session_id] = []

    # Refresh weather + tasks on greeting/activation
    lower_text = user_text.lower()
    if "selam" in lower_text or "aktif" in lower_text or "activate" in lower_text:
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})

    # First activation of a fresh session → deterministic clean greeting (no LLM).
    if len(conversations[session_id]) == 1 and (
        "selam" in lower_text or "aktif" in lower_text or "activate" in lower_text
    ):
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

    history = conversations[session_id][-16:]

    # LLM call
    reply = await llm_chat(get_system_prompt(), history, max_tokens=400)
    print(f"  LLM raw: {reply[:200]}", flush=True)
    spoken_text, action = extract_action(reply)

    # Speak the main response immediately
    if spoken_text:
        audio = await synthesize_speech(spoken_text)
        print(f"  E.V.: {spoken_text[:80]}", flush=True)
        print(f"  Audio bytes: {len(audio)}", flush=True)
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await ws.send_json({
            "type": "response",
            "text": spoken_text,
            "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
        })

    # Execute action if any
    if action:
        print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

        # Quick voice feedback for SCREEN so user knows E.V. is working
        if action["type"] == "SCREEN":
            hint = "Ekranına bir bakayım."
            hint_audio = await synthesize_speech(hint)
            await ws.send_json({
                "type": "response",
                "text": hint,
                "audio": base64.b64encode(hint_audio).decode("utf-8") if hint_audio else "",
            })

        try:
            action_result = await execute_action(action)
            print(f"  Result: {action_result}", flush=True)
        except Exception as e:
            print(f"  Action error: {e}", flush=True)
            action_result = f"Fehler: {e}"

        if action["type"] == "OPEN":
            # Just opened browser, nothing to summarize
            return

        # SEARCH, BROWSE, SCREEN — summarize results
        if action_result and "başarısız" not in action_result and "ulaşılamadı" not in action_result:
            summary = await llm_chat(
                f"Sen E.V.'sin. Aşağıdaki bilgileri KISA şekilde Türkçe özetle, en fazla 3 cümle, sakin ve sade E.V. tarzında. Kullanıcıya '{USER_ADDRESS}' diye ismiyle hitap et. Köşeli parantez içinde etiket YOK. ACTION etiketi YOK.",
                [{"role": "user", "content": f"Şunu özetle:\n\n{action_result}"}],
                max_tokens=250,
            )
            summary, _ = extract_action(summary)
        else:
            summary = f"Maalesef bu işe yaramadı, {USER_ADDRESS}."

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
    print(f"[E.V.] İstemci bağlandı", flush=True)

    try:
        while True:
            data = await ws.receive_json()

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
        conversations.pop(session_id, None)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


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
    }


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  E.V. — Voice AI Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
