# Changelog

Notable changes to E.V. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[SemVer](https://semver.org/).

## [1.0.1] — 2026-08-10

### Fixed
- English UI: with `language: "en"` in config, the dashboard chrome (panel
  labels, the workshop flavor log, and the "core initialized" line) rendered in
  Turkish unless `?lang=en` was passed in the URL. The default language was
  applied before `/stats` resolved and never re-rendered. All language-dependent
  text now re-renders once the server language is known.

### Docs
- Refreshed the dashboard screenshots for the regrouped stats layout (wind moved
  to the weather cluster).
- README: added the brain-benchmark and "how to use" sections to the Turkish
  half for parity with English; aligned the quoted `gemma2:9b` speed with the
  benchmark (~43 tok/s).

## [1.0.0] — 2026-08-10

First stable, tagged release. E.V. is a Windows-only, local-first voice
assistant: local Whisper STT, a local (Ollama) or Claude brain, ElevenLabs or
browser TTS, a deterministic PC-command router, long-term memory, and an
Electron cyber HUD. Free and offline by default.

This release hardens the app and makes the brain's quality measurable.

### Security
- Reject WebSocket handshakes whose `Origin` is not the HUD's own
  (`localhost`/`127.0.0.1:8340`), so a foreign page in the browser can't drive
  the assistant or bypass the spoken confirmation. Native clients (no `Origin`)
  still connect.
- An ambiguous reply to a destructive action now cancels instead of running;
  only a clean "yes" proceeds.
- `open_app` launches only apps from the known list — an arbitrary string is
  never handed to `start`.
- Electron grants only the microphone permission (camera, geolocation, etc.
  denied).
- The web-content summarizer is told the text is untrusted (prompt-injection
  hardening).

### Reliability
- Weather refresh runs off the event loop, so a greeting no longer freezes every
  request for several seconds.
- Playwright pages are closed after search/news (fixes a page/memory leak).
- Search queries are URL-encoded.
- History is trimmed to a token budget derived from `num_ctx` and always starts
  on a user turn (fixes silent context overflow and an Anthropic 400).
- `memory.json` is written atomically; the shared HTTP client and Playwright
  browser close on shutdown.

### Command router
- "don't forget X" now remembers instead of deleting a memory.
- "restart/reset" and bare "play/stop" require context, so "restart spotify"
  won't reboot the PC and "play a game" won't hit the media key.

### UI
- Dashboard stats regrouped: wind moved into the top-bar weather cluster, so the
  system panel shows only system metrics. Wind unit fixed to km/h (was
  mislabelled km/s).

### Tooling
- Added a pytest suite for the command router (43 cases).
- Added `eval/`: a reproducible (temperature-0) action-tag benchmark for the
  brain, a README results table, and a self-serve command to benchmark any
  model on your own card.

### Other
- Dependencies now carry upper version bounds so a stray install can't pull a
  breaking release.
- `config.json` gains optional `ollama_models_path` / `playwright_browsers_path`;
  these moved out of the hardcoded paths in the Electron launcher.

[1.0.0]: https://github.com/Ouru77/ev-assistant/releases/tag/v1.0.0
