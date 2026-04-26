"""RAGAS-based RAG evaluation of the Dossier query pipeline.

Follows the RAGAS RAG-eval quickstart — evaluating a deployed RAG pipeline
with four metrics:

- ``ContextRecall`` — did retrieval surface the claim the answer needs?
- ``ContextPrecisionWithReference`` — how much of the retrieved context is relevant?
- ``Faithfulness`` — is every claim in the answer grounded in the context?
- ``AnswerRelevancy`` — does the answer actually address the question?

The pipeline:
  1. Ingest fixture docs into a fresh Dossier project.
  2. For each hand-crafted ``(question, reference)`` pair: run
     ``dossier.query.query()`` to get candidates + hydrated prompt, produce
     an answer with gpt-4.1-mini (HMLR's tested model).
  3. Evaluate with RAGAS against the reference answer.
  4. Assert per-metric score floors.

We use hand-crafted test pairs rather than ``TestsetGenerator``. The generator
works but its internal ``HeadlineSplitter`` fails on short documents in
v0.4.3, and hand-crafted cases make the bench deterministic — the value of
RAGAS is the scoring, not the synthesis. A separate smoke test below exercises
the testset-gen path for anyone who wants to explore it on longer corpora.

Gated: ``pytest tests/bench/ --run-bench -k ragas`` with ``OPENAI_API_KEY`` set.
Cost: ~$0.10-0.30 per run on gpt-4o.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.bench

# Score floors the pipeline must clear. Conservative so the test is a
# regression detector rather than a perfectionism trap. Raise after we have
# 3-5 green runs to set the real bar.
# Score floors calibrated against the first green run on gpt-4o-mini (below).
# Raise after 3-5 stable runs, or when we switch back to gpt-4.1-mini. Each
# floor is set a few hundredths below the observed mean to absorb variance.
#
#   2026-04-24 gpt-4o-mini baseline (6 hand-crafted eval pairs):
#     context_recall:                  0.556
#     llm_context_precision_with_ref:  0.731
#     faithfulness:                    0.817
#     answer_relevancy:                0.962
MIN_CONTEXT_RECALL = 0.45
MIN_CONTEXT_PRECISION = 0.60
MIN_FAITHFULNESS = 0.70
MIN_ANSWER_RELEVANCY = 0.80

TESTSET_SIZE = 6  # only used by the testset-gen smoke test
EVAL_MODEL = os.environ.get("DOSSIER_BENCH_EVAL_MODEL", "gpt-4o-mini")
# HMLR's verified model is gpt-4.1-mini, but many OpenAI projects don't have
# 4.1-mini access by default. gpt-4o-mini is the widely available fallback.
# Override via env var once your project is granted 4.1-mini access.
ANSWER_MODEL = os.environ.get("DOSSIER_BENCH_ANSWER_MODEL", "gpt-4o-mini")

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


# Hand-crafted evaluation pairs.
#
# Split deliberately into three groups so regressions show which memory
# capability failed:
#
#   1. FACT recall    — single source, single claim
#   2. TEMPORAL recall — claim changed over time, which version is current?
#   3. MULTI-HOP      — answer joins two or more facts from different sources
#
# Questions 7-11 cannot be answered by naive retrieval on a single doc;
# they require the memory to have resolved entity identity across docs
# and tracked supersession.
EVAL_PAIRS: list[dict[str, str]] = [
    # --- fact recall (single-source) ---
    {
        "user_input": "Who built HMLR and what license is it under?",
        "reference": "HMLR was built by Sean VanWinkle and is licensed under MIT.",
    },
    {
        "user_input": "What are the three layers of the LLM Wiki pattern?",
        "reference": (
            "Raw sources (immutable documents), the wiki (LLM-generated markdown), "
            "and the schema (a configuration document like CLAUDE.md or AGENTS.md)."
        ),
    },
    {
        "user_input": "What is the core distinction between the LLM Wiki pattern and traditional RAG?",
        "reference": (
            "Traditional RAG retrieves from raw documents at query time. The LLM Wiki "
            "compiles knowledge once during ingestion so subsequent queries benefit from "
            "accumulated synthesis and cross-linking rather than repeating discovery work."
        ),
    },
    {
        "user_input": "What is the contradiction-resolution policy in Dossier?",
        "reference": (
            "Newer source wins by default, using last_updated as the tiebreaker. "
            "Pages marked confidence: high override older claims even when the new "
            "claim is more recent. True ties flag [[REVIEW]] and are not silently overwritten."
        ),
    },
    {
        "user_input": "Which model has HMLR been tested on?",
        "reference": "HMLR has only been verified on gpt-4.1-mini.",
    },
    {
        "user_input": "Why does Dossier keep the fact store in SQL instead of markdown?",
        "reference": (
            "Fast-changing key-value state like API keys, counters, and policy version "
            "numbers lives in a SQLite fact store. Wiki pages reference the fact store "
            "rather than duplicating these values."
        ),
    },
    # --- temporal / supersession ---
    {
        "user_input": "What is Alice Carter's current dietary preference, and when did it change?",
        "reference": (
            "Alice Carter is currently pescatarian. She was vegetarian until 2026-04-10, "
            "when she shifted on her doctor's recommendation. She still prefers Mediterranean food."
        ),
    },
    {
        "user_input": "What does the current team lunch policy require?",
        "reference": (
            "Under the v2 policy from 2026-04-18, team lunches must include at least "
            "two options, with one pescatarian and one fully vegetarian. The v1 policy "
            "(just two vegetarian options) has been superseded."
        ),
    },
    # --- multi-hop (join two docs) ---
    {
        "user_input": "Who built Quokka and what team does that person belong to?",
        "reference": (
            "Bob Navarro built Quokka. He is a senior engineer on Kelvin Cushman's "
            "memory-systems team, where he owns the ingestion pipeline."
        ),
    },
    {
        "user_input": "Who contributed the contradiction-visualisation panel to Quokka, and what other feature did they ship on the team?",
        "reference": (
            "Priya Shah contributed the contradiction-visualisation panel. Her "
            "previous feature on the team was the supersession-chain walker, which "
            "she built in her first month after joining in February 2026."
        ),
    },
    {
        "user_input": "Given Alice's dietary change, is the v1 vegetarian lunch policy still appropriate?",
        "reference": (
            "No. The v1 policy (two vegetarian options) was superseded by v2 on "
            "2026-04-18 specifically to accommodate Alice's shift to pescatarianism "
            "while still protecting strictly vegetarian team members like Priya."
        ),
    },
]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluator_llm() -> Any:
    """RAGAS evaluator LLM.

    We use ``LangchainLLMWrapper`` rather than ``llm_factory``. The former is
    marked deprecated in 0.4.3 but ``llm_factory`` returns an
    ``InstructorLLM`` whose interface doesn't match what the (also-deprecated)
    ``evaluate()`` function expects. Two deprecated APIs that disagree is
    worse than one. We'll switch when RAGAS' ``@experiment`` path matures.
    """
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(ChatOpenAI(model=EVAL_MODEL, temperature=0))


@pytest.fixture(scope="module")
def evaluator_embeddings() -> Any:
    """RAGAS embedding model — Langchain wrapper matches what ``evaluate()`` wants."""
    from langchain_openai import OpenAIEmbeddings as LCOpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    return LangchainEmbeddingsWrapper(LCOpenAIEmbeddings(model="text-embedding-3-small"))


@pytest.fixture(scope="module")
def answer_llm() -> Any:
    """Separate LLM used to actually answer the question given the Dossier prompt.

    Matches HMLR's only-tested model so scoring reflects the deployed stack
    rather than the evaluator stack.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=ANSWER_MODEL, temperature=0)


@pytest.fixture(scope="module")
def langchain_docs() -> list[Any]:
    """Load fixture sources as LangChain documents.

    The RAGAS quickstart uses ``DirectoryLoader``, but its default backend
    pulls in ``unstructured`` which is a heavy transitive dep. We point
    ``DirectoryLoader`` at ``TextLoader`` for markdown — same output shape,
    no extra install.
    """
    from langchain_community.document_loaders import DirectoryLoader, TextLoader

    assert FIXTURES.is_dir(), f"fixture dir missing: {FIXTURES}"
    loader = DirectoryLoader(
        str(FIXTURES),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    assert docs, f"no documents loaded from {FIXTURES}"
    return docs


@pytest.fixture(scope="module")
def dossier_project(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Fresh Dossier project rooted in a module-scoped tmp dir."""
    from dossier.config import DossierConfig

    root = tmp_path_factory.mktemp("dossier_bench")
    cfg = DossierConfig.for_root(root)
    cfg.ensure_dirs()
    # copy fixtures into the project's raw/ so ingest paths resolve
    for src in FIXTURES.glob("*.md"):
        (cfg.raw_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return cfg


@pytest.fixture(scope="module")
def ingested_project(dossier_project: Any) -> Any:
    """``dossier_project`` with every fixture ingested — the system under test."""
    from dossier.ingest import ingest_document

    for src in dossier_project.raw_dir.glob("*.md"):
        ingest_document(src, cfg=dossier_project)
    return dossier_project


@pytest.fixture(scope="module")
def testset(langchain_docs: list[Any], evaluator_llm: Any, evaluator_embeddings: Any) -> Any:
    """RAGAS testset generation. Module-scoped so multiple tests share one call.

    WARNING: ``HeadlineSplitter`` raises ``ValueError: 'headlines' property
    not found`` on our short fixture docs in v0.4.3. The smoke test that
    uses this fixture is marked to ``pytest.skip`` that specific error so
    the main eval test still runs.
    """
    from ragas.testset import TestsetGenerator

    generator = TestsetGenerator(llm=evaluator_llm, embedding_model=evaluator_embeddings)
    return generator.generate_with_langchain_docs(langchain_docs, testset_size=TESTSET_SIZE)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _retrieve_and_answer(question: str, cfg: Any, answer_llm: Any) -> tuple[str, list[str]]:
    """Run one question through Dossier and produce an answer.

    We do *not* use ``result.hydrated.prompt`` as-is — Dossier's default
    hydrator includes only one-line excerpts per candidate, which starves
    the answer LLM into refusing even when retrieval was perfect. Instead
    we reuse Dossier's retrieval + filtering and build a RAG-style prompt
    from the *full* wiki page bodies. That's what a real deployment would
    do: retrieve pointers with Dossier, read the full pages, answer.

    Returns ``(answer, retrieved_contexts)`` in the shape RAGAS wants.
    """
    from dossier.query import query

    result = query(question, cfg=cfg, limit=8)
    retrieved_contexts: list[str] = []
    for cand in result.candidates:
        text = _full_context_text(cand, cfg)
        retrieved_contexts.append(f"[{cand.kind}:{cand.ref}] {text}")

    prompt = _build_answer_prompt(question, retrieved_contexts)
    response = answer_llm.invoke(prompt)
    answer = response.content if hasattr(response, "content") else str(response)
    return answer, retrieved_contexts


def _build_answer_prompt(question: str, contexts: list[str]) -> str:
    """RAG-style prompt: full contexts, then the question, answer-only."""
    joined = "\n\n---\n\n".join(contexts)
    return (
        "You are answering using the provided context from the Dossier memory "
        "lattice. Answer the question based only on the context. If the answer "
        "is in the context, state it plainly and cite the source tag that "
        "precedes each context block (e.g. [wiki:entities/alice.md]). If the "
        "answer is not in the context, say so.\n\n"
        "## Context\n\n"
        f"{joined}\n\n"
        "## Question\n\n"
        f"{question}\n\n"
        "## Answer\n"
    )


def _full_context_text(cand: Any, cfg: Any, limit: int = 2048) -> str:
    """Load the full wiki page body for a wiki candidate; else use the excerpt."""
    if cand.kind != "wiki":
        return cand.text
    page_path = cfg.wiki_dir / cand.ref
    if not page_path.exists():
        return cand.text
    try:
        from dossier import frontmatter as fm

        page = fm.loads(page_path.read_text(encoding="utf-8"))
        body = page.body.strip()
    except Exception:
        body = page_path.read_text(encoding="utf-8")
    return body[:limit]


# ---------------------------------------------------------------------------
# the evaluation
# ---------------------------------------------------------------------------


def test_dossier_rag_pipeline_passes_ragas_floors(
    ingested_project: Any,
    evaluator_llm: Any,
    evaluator_embeddings: Any,
    answer_llm: Any,
    tmp_path: Path,
) -> None:
    """End-to-end: hand-crafted cases → Dossier answers → RAGAS metrics → score floors."""
    from ragas import EvaluationDataset, evaluate
    # The top-level ``ragas.metrics`` imports are marked deprecated in 0.4.3
    # ("use ragas.metrics.collections instead"), but the new collections
    # classes aren't ``Metric`` instances and ``evaluate()`` rejects them.
    # Stick with the documented RAG-eval quickstart path until RAGAS settles.
    from ragas.metrics import (  # noqa: I001
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )

    # Build evaluation samples from the hand-crafted pairs. Each pair has
    # ``user_input`` and a ``reference`` answer; we add Dossier-produced
    # ``retrieved_contexts`` and ``response``.
    samples: list[dict[str, Any]] = []
    for pair in EVAL_PAIRS:
        answer, contexts = _retrieve_and_answer(pair["user_input"], ingested_project, answer_llm)
        samples.append(
            {
                "user_input": pair["user_input"],
                "retrieved_contexts": contexts,
                "response": answer,
                "reference": pair["reference"],
            }
        )

    dataset = EvaluationDataset.from_list(samples)
    metrics = [
        LLMContextRecall(),
        LLMContextPrecisionWithReference(),
        Faithfulness(),
        ResponseRelevancy(),
    ]
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )

    # persist the raw table so humans can look at failing rows.
    df = result.to_pandas()
    out = tmp_path / "ragas_report.csv"
    df.to_csv(out, index=False)
    print(f"\nRAGAS report written to: {out}")
    print(df.to_string())

    # averaged per-metric scores
    scores = {col: float(df[col].mean()) for col in df.columns if df[col].dtype.kind == "f"}
    print("\nMean scores:")
    for k, v in scores.items():
        print(f"  {k:40s} {v:.3f}")

    # score-floor assertions — kept conservative; tighten after green runs
    _assert_floor(scores, "context_recall", MIN_CONTEXT_RECALL)
    _assert_floor(scores, "llm_context_precision", MIN_CONTEXT_PRECISION)
    _assert_floor(scores, "faithfulness", MIN_FAITHFULNESS)
    _assert_floor(scores, "answer_relevancy", MIN_ANSWER_RELEVANCY)


def _assert_floor(scores: dict[str, float], metric: str, floor: float) -> None:
    # metric names in the report vary across RAGAS versions — match by prefix.
    matches = [k for k in scores if metric.replace("_", "").lower() in k.replace("_", "").lower()]
    assert matches, f"metric not found in scores: {metric} (have: {list(scores)})"
    actual = scores[matches[0]]
    assert actual >= floor, f"{matches[0]} = {actual:.3f} < floor {floor:.3f}"


# ---------------------------------------------------------------------------
# lighter smoke: generate testset only (no evaluation), useful for dev
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "RAGAS 0.4.3 HeadlineSplitter raises ValueError('headlines' property "
        "not found) on short docs. Upstream bug — revisit after RAGAS update. "
        "Main eval test uses hand-crafted pairs and does not depend on this."
    ),
    strict=False,
)
def test_ragas_testset_generation_smoke(
    langchain_docs: list[Any], evaluator_llm: Any, evaluator_embeddings: Any
) -> None:
    """Just runs testset generation — catches RAGAS API drift without the full eval cost."""
    from ragas.testset import TestsetGenerator

    gen = TestsetGenerator(llm=evaluator_llm, embedding_model=evaluator_embeddings)
    ts = gen.generate_with_langchain_docs(langchain_docs, testset_size=2)
    df = ts.to_pandas()
    assert len(df) >= 1, "testset generator returned zero rows"
    assert "user_input" in df.columns, f"expected user_input column, got {list(df.columns)}"


if __name__ == "__main__":
    # Allow running directly: `python -m tests.bench.test_ragas_rag` from dossier/
    pytest.main([__file__, "--run-bench", "-s", "-v"])
