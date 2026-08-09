# E.V. — Your own local voice assistant 🛠️🎙️

> *A private, offline-first desktop voice assistant with a cyber "PC-dashboard" HUD — inspired by Peter Parker's homemade AI **E.V.** in Spider-Man: Brand New Day.*

E.V. runs **entirely on your own computer**. You talk (or type), it thinks, and it answers out loud. No cloud account required, no data leaving your machine by default. The look isn't flashy Stark holograms — it's a **grid-based cyber terminal**, in the spirit of a "budget genius" workshop.

Works in **English or Turkish** out of the box. It can also **control your PC** (open/close apps, media & volume, power) and **remembers things about you** between sessions.

*(Türkçe açıklama için [aşağıya bak](#türkçe).)*

---

## ✨ Features

- 🎙️ **Talk to it** — local **Whisper** speech recognition (offline, free). English or Turkish.
- 🧠 **Local brain** — a local LLM via **[Ollama](https://ollama.com)** (default `gemma2:9b`). Optionally plug in Claude for a smarter brain.
- 🔊 **Speaks back** — your browser's built-in voice (free) or **ElevenLabs** for a natural voice.
- 🖥️ **Cyber HUD** — an Electron desktop app: a compact corner **orb** or a full **dashboard** (system stats, clock, weather, live audio waveform, event log, terminal input).
- 🎛️ **Live audio core** — a circular visualizer that reacts to **your mic** while listening and to **E.V.'s voice** while speaking.
- 💻 **PC control** — "open Spotify", "turn it up", "next track", "lock the screen", "close Chrome". Destructive actions (closing apps, shutdown, running commands) **ask for confirmation first**.
- 🧠 **Long-term memory** — "remember that my favorite color is green" → E.V. recalls it in future sessions. "forget my coffee preference" clears it.
- 💬 **Conversation mode** — once you enable listening it stays in the conversation, then auto-mutes after a stretch of silence (safe while gaming).
- 🌐 **Web & screen** — web search / opening pages (Playwright) and optional screen description.
- 🔒 **Private** — with the default setup, nothing goes to the cloud; everything is local.
- 🔕 **Safe listening** — muted by default; toggle with `Ctrl+Space` so it never listens by accident.

## 🧩 Architecture

```
Mic → Whisper (STT, local) → FastAPI server
                                  │
                     command router (PC / memory) ─── deterministic, pre-LLM
                                  │
                            Ollama (LLM, local/GPU)
                                  │
        ┌─────────────────────────┼───────────────────────┐
   ElevenLabs / Browser       Playwright              Screen capture
        (TTS)                  (browser)               (optional)
                                  │
                    Electron HUD (WebSocket) ←→ browser
```

- **Backend:** Python + FastAPI + WebSocket (`server.py`)
- **STT:** `faster-whisper` (local, CPU)
- **LLM:** Ollama (local) or Anthropic Claude (optional)
- **TTS:** ElevenLabs or the browser Web Speech API
- **UI:** Electron + HTML/CSS/JS (`electron/`, `frontend/`)

## 🚀 Setup

**Requirements:** Windows 10/11, Python 3.10+, [Ollama](https://ollama.com), and (for the desktop app) Node.js.

```bash
# 1) Python dependencies
pip install -r requirements.txt
playwright install chromium

# 2) Local model (Ollama)
ollama pull gemma2:9b

# 3) Configuration
#    copy config.example.json  ->  config.json  and edit it.
#    Defaults are 100% free/local: Ollama + Whisper + browser voice. No keys needed.

# 4) Run
python server.py
#    Open http://localhost:8340 in a browser.
```

**Desktop app (Electron HUD):**

```bash
npm install
npm start
```

### Make it yours — `config.json`

The important bits:

```jsonc
{
  "language": "en",          // "en" (English) or "tr" (Türkçe)
  "user_name": "YOUR NAME",  // E.V. addresses you by this — so it won't say someone else's name 🙂
  "user_address": "YOUR NAME",
  "city": "London",          // used for the weather line

  "pc_control": true,        // allow open/close apps, media, power (with confirmation)
  "conversation_mode": true, // stay listening between turns, auto-mute when idle

  "tts_provider": "browser", // "browser" (free) or "elevenlabs"
  "llm_provider": "ollama"   // "ollama" (local) or "anthropic"
}
```

> 🗣️ **Important:** set `user_name` to *your* name. That's the name E.V. greets you with — otherwise it just uses a placeholder.

> Nicer voice: grab a free key from [elevenlabs.io](https://elevenlabs.io), put it in `config.json`, set `tts_provider` to `"elevenlabs"` and pick a `elevenlabs_voice_id`.
> Smarter brain: get a key from [console.anthropic.com](https://console.anthropic.com) and set `llm_provider` to `"anthropic"`.

## 🎮 How to use

1. Launch the app (or open `http://localhost:8340`).
2. Press **`Ctrl+Space`** (or click the core) to start listening — it's muted by default.
3. Talk. E.V. transcribes, thinks, and answers out loud.
4. Try things like:
   - *"What can you do?"*
   - *"Open the calculator."* · *"Close Chrome."* (asks to confirm)
   - *"Turn it up."* · *"Next track."* · *"Lock the screen."* (asks to confirm)
   - *"Remember that I take my coffee black."* → later: *"How do I take my coffee?"*

## 📁 Layout

```
server.py            FastAPI server (STT / LLM / TTS orchestration)
command_router.py    Deterministic TR/EN command routing (PC control + memory)
pc_control.py        Windows control: launch apps, media keys, power
strings.py           Bilingual (tr/en) prompts and spoken lines
whisper_stt.py       Local Whisper speech recognition
browser_tools.py     Playwright browser control
screen_capture.py    Screen description (optional)
frontend/            The UI (HUD + dashboard)
electron/            Desktop app shell
config.example.json  Example config (copy -> config.json)
```

## 🙏 Credits

Started from Julian Ivanov's [`jarvis-voice-assistant`](https://github.com/Julian-Ivanov/jarvis-voice-assistant) template, then substantially rewritten: E.V. identity, a fully-local (Ollama + Whisper) stack, the cyber dashboard, English/Turkish support, deterministic PC control, and long-term memory.

Character inspiration: *Spider-Man: Brand New Day* (E.V., voiced by Naomi Watts). This is a fan project, not affiliated with Marvel or Sony.

## 📜 License

[MIT](LICENSE) — do what you like, just keep the notice. See the LICENSE file for the template credit and fan-project note.

---

<a name="türkçe"></a>
# 🇹🇷 E.V. — Kendi bilgisayarında çalışan sesli asistan

E.V., tamamen **kendi bilgisayarında** çalışan, gizliliğe önem veren bir sesli asistandır. Konuşursun ya da yazarsın; anlar, düşünür ve sesle cevap verir. Arayüzü gösterişli hologramlar değil, **grid tabanlı siber bir terminal** — Peter'ın atölyesindeki "bütçesiz ama dahi" havasında. **Türkçe ve İngilizce** çalışır; ayrıca **bilgisayarını kontrol edebilir** (uygulama aç/kapat, ses/müzik, güç) ve **seninle ilgili şeyleri hatırlar**.

İsim ve karakter, *Spider-Man: Brand New Day*'deki Peter Parker'ın kendi yaptığı asistan **E.V.**'den esinlenir: sakin, zeki, mucit ruhlu.

## ✨ Özellikler

- 🎙️ **Sesle konuş** — yerel **Whisper** (offline, ücretsiz), Türkçe ya da İngilizce.
- 🧠 **Yerel beyin** — **Ollama** üzerinde yerel LLM (varsayılan `gemma2:9b`). İstersen Claude'a bağlanır.
- 🔊 **Sesli cevap** — tarayıcının yerleşik sesi (ücretsiz) ya da **ElevenLabs**.
- 🖥️ **Siber HUD** — Electron uygulaması: köşede kompakt **orb**, tam ekranda **dashboard**.
- 💻 **PC kontrolü** — "spotify aç", "sesi aç", "sonraki şarkı", "ekranı kilitle", "chrome'u kapat". Yıkıcı işlemler (kapatma, güç, komut) **önce onay ister**.
- 🧠 **Kalıcı hafıza** — "en sevdiğim rengi hatırla, yeşil" → sonraki oturumlarda hatırlar. "kahve tercihimi unut" ile siler.
- 💬 **Sohbet modu** — dinlemeyi açınca sohbette kalır, bir süre sessizlikte otomatik susar (oyun sırasında güvenli).
- 🔕 **Güvenli dinleme** — varsayılan sessiz; `Ctrl+Space` ile açılır.

## 🚀 Kurulum

```bash
pip install -r requirements.txt
playwright install chromium
ollama pull gemma2:9b
# config.example.json -> config.json (kopyala, düzenle; language: "tr")
python server.py            # http://localhost:8340
# Masaüstü uygulaması:
npm install && npm start
```

> `config.json` içinde `user_name` alanına **kendi adını** yaz — E.V. seni bu isimle selamlar. `language`'ı `"tr"` yap.
> Daha iyi ses için [elevenlabs.io](https://elevenlabs.io); Claude beyni için [console.anthropic.com](https://console.anthropic.com).

## 🙏 Teşekkür

[Julian Ivanov'un `jarvis-voice-assistant`](https://github.com/Julian-Ivanov/jarvis-voice-assistant) şablonu temel alınmış; ardından E.V. kimliği, yerel (Ollama + Whisper) yığın, siber dashboard, Türkçe/İngilizce destek, PC kontrolü ve hafıza eklenerek yeniden yazılmıştır. Karakter ilhamı: *Spider-Man: Brand New Day*. Bu bir hayran projesidir; Marvel/Sony ile bağlantısı yoktur.

## 📜 Lisans

[MIT](LICENSE).
