# E.V. — action-tag eval

A tiny benchmark for the **brain**: how reliably does the configured model emit
the correct `[ACTION:...]` tag for prompts that reach it (i.e. that the
deterministic router does *not* handle)?

It measures the actions only the model can produce — `SEARCH`, `NEWS`, `SCREEN` —
plus negative cases (ordinary chat that must produce **no** action). Every case
is checked to bypass the router, so the score reflects the model, not the rules.

The harness reuses the real server code (system prompt + `llm_chat` +
`extract_action`) and **never executes actions** — it only reads the tag the
model wrote. Running it is side-effect free.

## Run

```bash
# Ollama must be running and the model in config.json pulled.
python eval/run_eval.py
```

It prints per-category accuracy, an overall score, an approximate tok/s, and a
ready-to-paste README table row.

## Benchmark another model

1. Set `"ollama_model"` in `config.json` (e.g. `gemma2:9b`, `qwen2.5:7b`).
2. `ollama pull <model>` if you haven't.
3. `python eval/run_eval.py` again.

Each run reads the current config, so the score matches that model. The cases
live in `eval/cases.py` (bilingual; the set matching `config.language` is used).

> Note: this loads the model into VRAM. Run it when the GPU is free.
