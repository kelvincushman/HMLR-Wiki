"""autoresearch harness — run one RAGAS experiment, log the result.

Reads ``strategy.py`` (imported fresh each run so edits take effect), runs
the 6 hand-crafted eval pairs from the RAGAS bench, scores with RAGAS, and
appends one row to ``log.jsonl``.

Usage:
    cd dossier
    python autoresearch/run_experiment.py

Cost: ~$0.05-0.15 per run. Requires ``OPENAI_API_KEY``.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "bench"))

LOG_PATH = HERE / "log.jsonl"
FIXTURES = REPO_ROOT / "tests" / "bench" / "fixtures" / "raw"

# RAGAS judge + embeddings always run on OpenAI for comparability. The
# ANSWER model can be any OpenAI-compatible endpoint (OpenAI, OpenRouter,
# Together, Groq, Anyscale, Fireworks, local vLLM, etc.).
EVAL_MODEL = os.environ.get("DOSSIER_BENCH_EVAL_MODEL", "gpt-4o-mini")
ANSWER_MODEL = os.environ.get("DOSSIER_BENCH_ANSWER_MODEL", "gpt-4o-mini")

# If set, the answer model is routed through this URL + key instead of OpenAI.
# Example for OpenRouter:
#   DOSSIER_ANSWER_BASE_URL=https://openrouter.ai/api/v1
#   DOSSIER_ANSWER_API_KEY=sk-or-v1-...
#   DOSSIER_BENCH_ANSWER_MODEL=anthropic/claude-3.5-haiku
ANSWER_BASE_URL = os.environ.get("DOSSIER_ANSWER_BASE_URL")  # None => OpenAI default
ANSWER_API_KEY = os.environ.get("DOSSIER_ANSWER_API_KEY") or os.environ.get("OPENAI_API_KEY")


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    # late imports so --help etc are cheap
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings as LCOpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )

    from dossier.config import DossierConfig

    # memory.py owns the full pipeline — the agent edits that file.
    import memory  # type: ignore  # noqa: E402
    importlib.reload(memory)

    # Re-import EVAL_PAIRS from the bench module.
    import test_ragas_rag  # type: ignore  # noqa: E402
    importlib.reload(test_ragas_rag)
    eval_pairs = test_ragas_rag.EVAL_PAIRS

    note = (memory.__doc__ or "").strip().splitlines()
    experiment_note = next(
        (ln.partition(":")[2].strip() for ln in note if ln.startswith("EXPERIMENT_NOTE")),
        "(no EXPERIMENT_NOTE docstring)",
    )

    # Bootstrap a fresh project in a tmp dir per run, using memory.ingest so
    # the agent's changes to extraction actually take effect.
    tmp = Path(tempfile.mkdtemp(prefix="autoresearch_"))
    cfg = DossierConfig.for_root(tmp)
    cfg.ensure_dirs()
    for src in FIXTURES.glob("*.md"):
        (cfg.raw_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    ingest_summaries = []
    for src in sorted(cfg.raw_dir.glob("*.md")):
        ingest_summaries.append(memory.ingest(src, cfg))

    # Wiki-side consolidation pass (exp-L). No-op if USE_WIKI_SYNTHESIS=False
    # or if no multi-source pages exist. Runs once, after all ingests.
    if hasattr(memory, "consolidate"):
        consolidate_summary = memory.consolidate(cfg)
    else:
        consolidate_summary = {}

    # Build LLM wrappers.
    evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model=EVAL_MODEL, temperature=0))
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        LCOpenAIEmbeddings(model="text-embedding-3-small")
    )

    # Answer model: point at OpenRouter (or any OpenAI-compatible proxy) when
    # DOSSIER_ANSWER_BASE_URL is set; otherwise use OpenAI directly.
    answer_kwargs: dict[str, Any] = {"model": ANSWER_MODEL, "temperature": 0}
    if ANSWER_BASE_URL:
        answer_kwargs["base_url"] = ANSWER_BASE_URL
        answer_kwargs["api_key"] = ANSWER_API_KEY
    answer_llm = ChatOpenAI(**answer_kwargs)

    t0 = time.time()
    samples = []
    for pair in eval_pairs:
        question = pair["user_input"]
        contexts = memory.retrieve(question, cfg)
        prompt = memory.build_prompt(question, contexts)
        response = answer_llm.invoke(prompt)
        raw_answer = response.content if hasattr(response, "content") else str(response)
        answer = memory.synthesize(raw_answer, contexts, question)
        samples.append(
            {
                "user_input": question,
                "retrieved_contexts": [f"[{c['kind']}:{c['ref']}] {c['text']}" for c in contexts],
                "response": answer,
                "reference": pair["reference"],
            }
        )

    dataset = EvaluationDataset.from_list(samples)
    report = evaluate(
        dataset=dataset,
        metrics=[
            LLMContextRecall(),
            LLMContextPrecisionWithReference(),
            Faithfulness(),
            ResponseRelevancy(),
        ],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )
    wall_s = time.time() - t0

    df = report.to_pandas()
    scores = {col: float(df[col].mean()) for col in df.columns if df[col].dtype.kind == "f"}
    composite = sum(scores.values()) / len(scores) if scores else 0.0

    toggles = {
        name: getattr(memory, name)
        for name in (
            "USE_LLM_EXTRACTORS",
            "USE_EMBEDDING_RETRIEVAL",
            "USE_QUERY_DECOMPOSITION",
            "USE_HYBRID_RERANK",
            "USE_ENTITY_CENTRIC_BOOST",
            "USE_LLM_RERANK",
            "USE_WIKI_SYNTHESIS",
            "USE_RAW_SOURCE_FLOOR",
            "USE_LLM_SYNTHESIS",
        )
        if hasattr(memory, name)
    }
    ingest_totals: dict[str, int] = {"entities": 0, "concepts": 0, "facts": 0}
    for s in ingest_summaries:
        for k in ingest_totals:
            ingest_totals[k] += int(s.get(k, 0))
    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "experiment_note": experiment_note,
        "eval_model": EVAL_MODEL,
        "answer_model": ANSWER_MODEL,
        "answer_provider": ANSWER_BASE_URL or "openai",
        "toggles": toggles,
        "ingest_totals": ingest_totals,
        "consolidate": consolidate_summary,
        "wall_seconds": round(wall_s, 1),
        "composite": round(composite, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "n_samples": len(samples),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    print()
    print(f"experiment note: {experiment_note}")
    print(f"wall time:       {wall_s:.1f}s")
    print("scores:")
    for k, v in sorted(scores.items()):
        print(f"  {k:40s} {v:.3f}")
    print(f"composite:       {composite:.3f}")
    print(f"logged to:       {LOG_PATH}")

    # compare to best so far (composite)
    if LOG_PATH.exists():
        best = None
        best_row = None
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                prev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if best is None or prev["composite"] > best:
                best = prev["composite"]
                best_row = prev
        if best_row is not None:
            delta = composite - best
            marker = "*" if composite >= best else " "
            print(f"{marker} best so far:  {best:.3f} ({best_row['experiment_note'][:60]})")
            print(f"  delta:         {delta:+.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
