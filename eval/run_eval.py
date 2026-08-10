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
    """Run one prompt and grade the tag. Returns (got, elapsed, gen_tok_s).

    For Ollama we call /api/chat directly (mirroring server.llm_chat's ollama path)
    so we can read Ollama's own eval_count/eval_duration and report *pure generation*
    tok/s — not a wall-clock estimate skewed by the large system prompt. Grading still
    uses the real system prompt + extract_action, so behavior matches the app.
    """
    t0 = time.perf_counter()
    gen_tok_s = 0.0
    if server.LLM_PROVIDER == "ollama":
        payload = {
            "model": server.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": server.get_system_prompt()},
                {"role": "user", "content": phrase},
            ],
            "stream": False, "keep_alive": "30m",
            # temperature=0 (greedy) for a REPRODUCIBLE benchmark. The app itself
            # uses 0.7 for conversation; here we want a stable, comparable score.
            "options": {"num_predict": 200, "temperature": 0.0, "num_ctx": server.NUM_CTX},
        }
        resp = await server.http.post(f"{server.OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        j = resp.json()
        text = j["message"]["content"]
        ec, ed = j.get("eval_count") or 0, j.get("eval_duration") or 0  # ed in ns
        gen_tok_s = ec / (ed / 1e9) if ed else 0.0
    else:
        text = await server.llm_chat(server.get_system_prompt(),
                                     [{"role": "user", "content": phrase}], max_tokens=200)
    elapsed = time.perf_counter() - t0
    _, action = server.extract_action(text)
    got = action["type"] if action else None
    return got, elapsed, gen_tok_s


async def main():
    lang = server.LANGUAGE
    dataset = cases.CASES.get(lang, cases.CASES["en"])
    # Benchmark a specific model without editing config.json:
    #   EV_EVAL_MODEL=aya-expanse:8b python eval/run_eval.py
    override = os.environ.get("EV_EVAL_MODEL")
    if override:
        server.OLLAMA_MODEL = override
    model = server.OLLAMA_MODEL if server.LLM_PROVIDER == "ollama" else "claude"

    print("=" * 64)
    print(f"  E.V. action-tag eval  ·  provider={server.LLM_PROVIDER}  model={model}  lang={lang}")
    print(f"  {len(dataset)} cases · this calls the local model (GPU). Ctrl+C to abort.")
    print("=" * 64)

    per_cat = {}          # category -> [correct, total]
    failures = []
    total_time = 0.0
    tok_s_samples = []

    for i, (phrase, expected) in enumerate(dataset, 1):
        cat = expected or "NONE"
        try:
            got, elapsed, gen_tok_s = await _grade_one(phrase, expected)
        except Exception as e:
            print(f"  [{i:2}] ERROR calling model: {str(e)[:120]}")
            print("  Is Ollama running and the model pulled? Aborting.")
            return
        total_time += elapsed
        if gen_tok_s > 0:
            tok_s_samples.append(gen_tok_s)
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
    gen_tok_s = sum(tok_s_samples) / len(tok_s_samples) if tok_s_samples else 0.0
    avg_latency = total_time / total if total else 0.0

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
    print(f"  GEN SPEED: ~{gen_tok_s:.0f} tok/s (Ollama eval metrics, generation only)")
    print(f"  LATENCY  : ~{avg_latency:.1f} s per query (end-to-end, incl. prompt)")
    print("-" * 64)
    # Ready-to-paste README table row.
    print("  README row:")
    print(f"  | `{model}` | {acc:.0f}% | ~{gen_tok_s:.0f} tok/s | _fill VRAM_ |")
    print("=" * 64)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted.")
