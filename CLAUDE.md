# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

E.V. is a **Windows-only**, local-first voice assistant: a Python/FastAPI + WebSocket server that does local Whisper STT, a local (Ollama) or Claude brain, ElevenLabs/browser TTS, deterministic PC control, and long-term memory, wrapped in an Electron "cyber HUD". Runs at `http://localhost:8340` (server binds to `127.0.0.1` only).

## Commands

```bash
# Run the server (needs the venv + Ollama running)
python server.py                      # serves http://localhost:8340

# Dependencies
pip install -r requirements.txt
playwright install chromium
ollama pull gemma2:9b

# Desktop app (Electron HUD)
npm install
npm start
```

- **Config:** copy `config.example.json` -> `config.json` and edit. `config.json` and `memory.json` are gitignored and hold secrets/personal data; never commit them. `strings.py` holds a `_S` map for adding languages.
- **Model/browser caches** are redirected off the system drive via the `OLLAMA_MODELS` and `PLAYWRIGHT_BROWSERS_PATH` env vars (this setup points them at a large data drive). Electron's `main.js` sets them when it spawns the server; set them yourself when running `server.py` directly.
- **No automated test suite.** Verify changes by connecting to `ws://localhost:8340/ws` with a small script (send `{"text": "..."}`, read `response_chunk`/`response_done`), or screenshot the HUD with a headless Playwright script. Restarting the server reloads the model into VRAM (a warm-up runs at startup).

## Architecture (the big picture)

**Everything flows through `server.py::process_message`.** The order of that function is the key to understanding the app:

1. **Pending-confirm check** — if a destructive action is awaiting a yes/no, this turn is read as the answer (`_YES`/`_NO`, both languages).
2. **Greeting** — a deterministic, non-LLM greeting on first activation.
3. **Deterministic command router (`command_router.py`) runs BEFORE the LLM.** This is the central design decision: small local models (gemma2:9b) do **not** reliably emit `[ACTION:...]` tags, so explicit imperatives ("chrome'u kapat", "play X on YouTube", "remember Y") are regex-matched per-language and turned into action dicts directly, so they work every time. Only conversational input falls through to the model.
4. **LLM path** — `llm_stream` (Ollama, streaming) yields tokens; `process_message` splits on sentence boundaries and calls `speak_chunk` so E.V. starts talking before the full reply is done. `[ACTION:...]` tags the model *does* emit are parsed at the end.

**Actions** (`execute_action`) are split into non-destructive (run immediately) and `DESTRUCTIVE_ACTIONS` = {CLOSE, POWER, CMD} (stashed in `pending_actions`, spoken confirm question sent, resolved on the next yes/no). Action results prefixed with `__SPOKEN__` are spoken verbatim; others get summarized by the LLM.

**Subsystems:**
- `command_router.py` — TR + EN regex routing for PC/memory commands. `route(text, lang)`. Targeted clicks ("click *that video*") deliberately do NOT route, so the LLM refuses honestly instead of clicking blindly.
- `pc_control.py` — Windows control via `ctypes`: launch/close apps, media & volume (virtual key events), power, mouse, and `fullscreen_active()` (SHQueryUserNotificationState). Language-aware via `set_language()`.
- `strings.py` — **all** spoken text and the full system prompt, in `tr`/`en`, selected by `config.language`. Adding a language = add a column here + a branch in the system-prompt/greeting functions.
- `whisper_stt.py` — faster-whisper on CPU; language from config.
- `browser_tools.py` — Playwright (search/visit/news) + `youtube_open` (scrapes the first videoId from results HTML, opens the watch URL in the default browser).
- `screen_capture.py` — screen description via Claude vision (optional; needs an Anthropic key).
- `frontend/` — the HUD (`main.js`, `index.html`, `style.css`). UI is i18n'd via `data-i18n` attributes + an `I18N`/`STR` map; `appLang` comes from `/stats` (or a `?lang=` override). The center canvas visualizer reacts to the mic while listening and to E.V.'s voice while speaking.
- `electron/` — frameless/transparent/always-on-top desktop shell that spawns the venv server, registers a global `Ctrl+Space` toggle, and manages compact/dashboard modes.

**Cross-cutting details worth knowing:**
- **Long-term memory** = `memory.json` (`{"facts": [...]}`), injected into the system prompt every turn so remembered facts never drift out of context. Raw conversation is a rolling window of `history_turns` messages.
- **VRAM fallback:** `llm_chat`/`llm_stream` try the configured `num_ctx`, then retry at Ollama's default if the GPU is tight (e.g. a game is running) so E.V. answers instead of erroring.
- **Fullscreen auto-tray:** a background task polls `fullscreen_active()` and broadcasts `{"type":"fullscreen"}` to all `clients`; the frontend hides/restores the Electron window.
- **Config keys that change behavior:** `llm_provider` (ollama|anthropic), `tts_provider` (browser|elevenlabs), `stt_provider`, `language` (tr|en), `pc_control`, `conversation_mode`, `history_turns`, `num_ctx`, `user_name`/`city`.

## Notes

- This is a fan project based on Julian Ivanov's `jarvis-voice-assistant` template (credited in README). Persona: calm, understated DIY inventor (E.V. from Spider-Man: Brand New Day), addresses the user by first name, never formal.
- The default stack is fully free/local (Ollama + Whisper + browser voice, no keys). ElevenLabs (voice) and Claude (brain + screen vision) are optional upgrades.
