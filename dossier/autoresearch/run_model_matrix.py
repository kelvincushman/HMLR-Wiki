"""Run the baseline strategy against a matrix of answer models.

Holds retrieval + prompt fixed (whatever is in ``strategy.py``), varies only
the answer model. RAGAS judge + embeddings stay on OpenAI so scores are
comparable across models. Results append to ``log.jsonl`` alongside the
single-run experiments.

Usage:
    export OPENAI_API_KEY=sk-...              # judge + embeddings
    export DOSSIER_ANSWER_API_KEY=sk-or-...   # OpenRouter for answer model
    python autoresearch/run_model_matrix.py

Skip models via ``--only "anthropic/*,openai/*"`` or ``--skip "google/*"``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (provider, model, base_url) — one row per answer model.
# OpenAI rows use no base_url; OpenRouter rows use the OR endpoint.
OPENROUTER_URL = "https://openrouter.ai/api/v1"
MATRIX: list[tuple[str, str, str | None]] = [
    # OpenAI direct (baseline — uses OPENAI_API_KEY as answer key)
    ("openai-direct", "gpt-4o-mini", None),
    # OpenAI via OpenRouter — same models, different plumbing. Lets us test
    # gpt-4.1-mini (HMLR's verified model) when the user's OpenAI project
    # doesn't have direct 4.1-mini access.
    ("openrouter", "openai/gpt-4o-mini", OPENROUTER_URL),
    ("openrouter", "openai/gpt-4.1-mini", OPENROUTER_URL),
    # OpenRouter — cross-provider comparison
    ("openrouter", "google/gemini-2.0-flash-001", OPENROUTER_URL),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct", OPENROUTER_URL),
    ("openrouter", "anthropic/claude-3.5-haiku", OPENROUTER_URL),
    ("openrouter", "qwen/qwen-2.5-72b-instruct", OPENROUTER_URL),
    ("openrouter", "deepseek/deepseek-chat", OPENROUTER_URL),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="Comma-separated model substrings to include")
    parser.add_argument("--skip", help="Comma-separated model substrings to exclude")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY required for RAGAS judge + embeddings", file=sys.stderr)
        return 2

    only = [s.strip() for s in (args.only or "").split(",") if s.strip()]
    skip = [s.strip() for s in (args.skip or "").split(",") if s.strip()]

    selected: list[tuple[str, str, str | None]] = []
    for provider, model, url in MATRIX:
        if only and not any(s in model for s in only):
            continue
        if skip and any(s in model for s in skip):
            continue
        if url == OPENROUTER_URL and not os.environ.get("DOSSIER_ANSWER_API_KEY"):
            print(f"  skip {model}: DOSSIER_ANSWER_API_KEY not set", file=sys.stderr)
            continue
        selected.append((provider, model, url))

    if not selected:
        print("no models selected", file=sys.stderr)
        return 2

    print(f"running {len(selected)} models:")
    for p, m, _ in selected:
        print(f"  [{p}] {m}")
    print()

    fails: list[tuple[str, str]] = []
    for provider, model, url in selected:
        print(f"=== [{provider}] {model} ===")
        env = dict(os.environ)
        env["DOSSIER_BENCH_ANSWER_MODEL"] = model
        if url:
            env["DOSSIER_ANSWER_BASE_URL"] = url
        else:
            env.pop("DOSSIER_ANSWER_BASE_URL", None)
        rc = subprocess.call(
            [sys.executable, str(HERE / "run_experiment.py")],
            env=env,
        )
        if rc != 0:
            fails.append((model, f"exit {rc}"))
        print()

    print("=" * 60)
    print("matrix done.")
    if fails:
        print("failures:")
        for m, why in fails:
            print(f"  {m}: {why}")
    print(f"\nsee {HERE / 'log.jsonl'} for all rows.")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
