"""
E.V. — LLM action-tag eval harness.

Measures how reliably the configured brain (an Ollama model, or Claude) emits the
correct [ACTION:...] tag for prompts that BYPASS the deterministic router and
reach the model. This is the honest "is the small local model good enough for the
job" number that feeds the README benchmark table.

It reuses the real server code paths (system prompt + llm_chat + extract_action),
so the score reflects actual behavior. It NEVER executes actions — it only reads
the tag the model produced — so running it is completely side-effect free.

Usage (from the repo root):
    # 1) make sure Ollama is running and the model in config.json is pulled
    python eval/run_eval.py

Benchmark another model: set "ollama_model" in config.json, `ollama pull` it, and
run again. Each run reads the current config, so the score matches that model.
"""

import asyncio
import os
import sys
import time

# Put the repo root on the path so `import server` works when this is run as
# `python eval/run_eval.py` (the script's own dir is already on sys.path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402  (path must be set first)
import cases   # noqa: E402


async def _grade_one(phrase: str, expected):
    """Run one prompt through the real model path; return (got, elapsed, chars)."""
    messages = [{"role": "user", "content": phrase}]
    t0 = time.perf_counter()
    text = await server.llm_chat(server.get_system_prompt(), messages, max_tokens=200)
    elapsed = time.perf_counter() - t0
    _, action = server.extract_action(text)
    got = action["type"] if action else None
    return got, elapsed, len(text)


async def main():
    lang = server.LANGUAGE
    dataset = cases.CASES.get(lang, cases.CASES["en"])
    model = server.OLLAMA_MODEL if server.LLM_PROVIDER == "ollama" else "claude"

    print("=" * 64)
    print(f"  E.V. action-tag eval  ·  provider={server.LLM_PROVIDER}  model={model}  lang={lang}")
    print(f"  {len(dataset)} cases · this calls the local model (GPU). Ctrl+C to abort.")
    print("=" * 64)

    per_cat = {}          # category -> [correct, total]
    failures = []
    total_time = 0.0
    total_chars = 0

    for i, (phrase, expected) in enumerate(dataset, 1):
        cat = expected or "NONE"
        try:
            got, elapsed, chars = await _grade_one(phrase, expected)
        except Exception as e:
            print(f"  [{i:2}] ERROR calling model: {str(e)[:120]}")
            print("  Is Ollama running and the model pulled? Aborting.")
            return
        total_time += elapsed
        total_chars += chars
        ok = (got == expected)
        c = per_cat.setdefault(cat, [0, 0])
        c[1] += 1
        if ok:
            c[0] += 1
        else:
            failures.append((phrase, expected, got))
        mark = "ok " if ok else "XX "
        print(f"  [{i:2}] {mark} exp={str(expected):7} got={str(got):7} | {phrase[:44]}")

    # --- summary ---
    correct = sum(v[0] for v in per_cat.values())
    total = sum(v[1] for v in per_cat.values())
    acc = 100.0 * correct / total if total else 0.0
    approx_toks = total_chars / 4.0
    tok_s = approx_toks / total_time if total_time else 0.0

    print("-" * 64)
    print("  By category:")
    for cat in ("SEARCH", "NEWS", "SCREEN", "NONE"):
        if cat in per_cat:
            good, tot = per_cat[cat]
            print(f"    {cat:8} {good}/{tot}  ({100.0*good/tot:.0f}%)")
    if failures:
        print("  Misses:")
        for phrase, exp, got in failures:
            print(f"    exp={str(exp):7} got={str(got):7} | {phrase[:50]}")

    print("-" * 64)
    print(f"  ACCURACY : {correct}/{total}  ({acc:.1f}%)")
    print(f"  SPEED    : ~{tok_s:.0f} tok/s (wall-clock, approx)")
    print("-" * 64)
    # Ready-to-paste README table row.
    print("  README row:")
    print(f"  | `{model}` | {acc:.0f}% | ~{tok_s:.0f} | _fill VRAM_ |")
    print("=" * 64)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted.")
