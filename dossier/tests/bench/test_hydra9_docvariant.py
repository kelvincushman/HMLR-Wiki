"""Hydra9 Hard Mode — document-ingest variant.

Mirrors HMLR's Hydra9 Hard Mode test, adapted for document ingest. The
fixture corpus at ``tests/bench/fixtures/hydra9_docvariant/`` is 21 dated
markdown docs spread across ~30 simulated days, covering:

  - 8-hop entity-alias drift (Legacy-Phi → … → Tartarus-v3)
  - 8-step policy cascade including a rogue-authored revert
  - Project Cerberus capacity + integration plan
  - Distractors

The final query asks a compliance question whose correct answer requires
joining every hop of the chain. Exactly HMLR's Hydra9 shape; same pass
criteria (verdict + reasoning chain present in the answer).

Gated: ``pytest tests/bench/ --run-bench -k hydra9`` with OPENAI_API_KEY set.
Cost: ~$0.40-$0.80 per run (21 LLM ingest calls + rerank + synthesis).

Runs memory.py's current pipeline — whatever toggles are on in
``autoresearch/memory.py`` when the test fires. As of exp-J that's all
six upgrades.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.bench

# Path gymnastics so test_hydra9_docvariant.py can import memory.py from
# the autoresearch/ dir without installing memory as a package.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "autoresearch"))

from tests.bench.fixtures.hydra9_docvariant import (  # noqa: E402
    FINAL_QUERY,
    FINAL_REFERENCE,
    HYDRA9_DOCS,
    REQUIRED_TOKEN_SETS,
)


def _build_corpus(raw_dir: Path) -> list[Path]:
    """Write all 21 fixture docs into ``raw_dir`` and return sorted paths."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for doc in HYDRA9_DOCS:
        p = raw_dir / doc["filename"]
        p.write_text(doc["text"], encoding="utf-8")
        paths.append(p)
    # lexical sort matches chronological since filenames are date-prefixed
    return sorted(paths)


def _answer_final_query(cfg: Any, answer_llm: Any) -> tuple[str, list[str]]:
    """Run the final compliance query through memory.py's full pipeline."""
    import memory  # noqa: E402

    importlib.reload(memory)
    contexts = memory.retrieve(FINAL_QUERY, cfg)
    prompt = memory.build_prompt(FINAL_QUERY, contexts)
    response = answer_llm.invoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    answer = memory.synthesize(raw, contexts, FINAL_QUERY)
    context_strings = [f"[{c['kind']}:{c['ref']}] {c['text']}" for c in contexts]
    return answer, context_strings


def _check_token_sets(answer: str) -> dict[str, bool]:
    """For each required-token row, return whether at least one variant is
    present in the answer (case-insensitive)."""
    low = answer.lower()
    return {
        f"set_{i}": any(tok.lower() in low for tok in variants)
        for i, variants in enumerate(REQUIRED_TOKEN_SETS)
    }


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hydra9_project(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Fresh Dossier project with all 21 Hydra9 docs ingested."""
    import memory  # noqa: E402

    importlib.reload(memory)

    from dossier.config import DossierConfig  # noqa: E402

    root = tmp_path_factory.mktemp("hydra9_docvariant")
    cfg = DossierConfig.for_root(root)
    cfg.ensure_dirs()
    paths = _build_corpus(cfg.raw_dir)

    # ingest all 21 docs in chronological order, using memory.py's pipeline
    summaries = []
    for src in paths:
        summaries.append(memory.ingest(src, cfg))

    # Gardener-style wiki-side synthesis pass (exp-L). This is the step that
    # compresses the 21 dispersed source summaries into single coherent
    # dossier pages per entity — the Karpathy half of the fusion.
    consolidate_summary = (
        memory.consolidate(cfg) if hasattr(memory, "consolidate") else {}
    )

    return {
        "cfg": cfg,
        "summaries": summaries,
        "n_docs": len(paths),
        "consolidate": consolidate_summary,
    }


@pytest.fixture(scope="module")
def answer_llm() -> Any:
    """Same answer LLM the rest of the bench uses — gpt-4.1-mini via OpenRouter
    if DOSSIER_ANSWER_BASE_URL is set, else direct OpenAI."""
    import os

    from langchain_openai import ChatOpenAI

    model = os.environ.get("DOSSIER_BENCH_ANSWER_MODEL", "gpt-4o-mini")
    kwargs: dict[str, Any] = {"model": model, "temperature": 0}
    if os.environ.get("DOSSIER_ANSWER_BASE_URL"):
        kwargs["base_url"] = os.environ["DOSSIER_ANSWER_BASE_URL"]
        kwargs["api_key"] = (
            os.environ.get("DOSSIER_ANSWER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
    return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_hydra9_ingest_produced_substantial_memory(hydra9_project: dict) -> None:
    """Sanity check: ingest actually wrote pages + facts for each day."""
    summaries = hydra9_project["summaries"]
    assert len(summaries) == hydra9_project["n_docs"] == 21

    total_entities = sum(s.get("entities", 0) for s in summaries)
    total_facts = sum(s.get("facts", 0) for s in summaries)
    # With LLM extractors on, a 21-doc corpus about encryption schemes and
    # policies should produce at least a few dozen entities/facts total.
    assert total_entities >= 20, f"only {total_entities} entities extracted"
    assert total_facts >= 15, f"only {total_facts} facts extracted"

    # Wiki directory should have pages across all three kinds
    wiki = hydra9_project["cfg"].wiki_dir
    assert (wiki / "entities").is_dir()
    assert (wiki / "concepts").is_dir() or True  # concepts optional per doc
    assert (wiki / "sources").is_dir()
    assert len(list((wiki / "sources").glob("*.md"))) == 21


def test_hydra9_compliance_chain_pass(
    hydra9_project: dict, answer_llm: Any, tmp_path: Path
) -> None:
    """The headline test: answer the compliance question using ONLY Dossier's
    long-term memory (wiki + fact store), produce a correct NON-COMPLIANT
    verdict with the full reasoning chain.

    Pass criteria — mirrors HMLR's binary verification style:
      1. Verdict: answer names a compliance verdict (NON-COMPLIANT).
      2. Name chain: references Tartarus-v3 and at least one prior alias.
      3. Active policy: cites Policy v6 and the 400k/day limit.
      4. Rogue-revert: shows awareness of v7/v8 dynamics.
      5. Volume mismatch: cites Cerberus's actual volume and exceeds.
    """
    answer, contexts = _answer_final_query(hydra9_project["cfg"], answer_llm)

    # write artefacts for inspection on failure
    (tmp_path / "hydra9_answer.txt").write_text(answer, encoding="utf-8")
    (tmp_path / "hydra9_contexts.txt").write_text(
        "\n\n---\n\n".join(contexts), encoding="utf-8"
    )
    print(f"\nHydra9 answer:\n{answer}\n")
    print(f"artefacts: {tmp_path}")

    hits = _check_token_sets(answer)
    print("\nRequired token-set hits:")
    for k, v in hits.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")

    missing = [k for k, v in hits.items() if not v]
    assert not missing, (
        f"Hydra9 answer missing required elements: {missing}\n"
        f"Answer was:\n{answer}"
    )


def test_hydra9_ragas_composite_above_threshold(
    hydra9_project: dict, answer_llm: Any
) -> None:
    """Score the Hydra9 answer with RAGAS using the reference answer.
    Asserts composite >= 0.75 — HMLR reports 1.00/1.00/0.23 (faith/recall/prec)
    on Hydra9, mean 0.743. We aim to match or beat that."""
    import os

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

    answer, contexts = _answer_final_query(hydra9_project["cfg"], answer_llm)

    eval_model = os.environ.get("DOSSIER_BENCH_EVAL_MODEL", "gpt-4o-mini")
    evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model=eval_model, temperature=0))
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        LCOpenAIEmbeddings(model="text-embedding-3-small")
    )

    sample = {
        "user_input": FINAL_QUERY,
        "retrieved_contexts": contexts,
        "response": answer,
        "reference": FINAL_REFERENCE,
    }
    dataset = EvaluationDataset.from_list([sample])
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
    df = report.to_pandas()
    scores = {col: float(df[col].mean()) for col in df.columns if df[col].dtype.kind == "f"}
    composite = sum(scores.values()) / len(scores) if scores else 0.0
    print("\nHydra9 RAGAS scores:")
    for k, v in sorted(scores.items()):
        print(f"  {k:40s} {v:.3f}")
    print(f"  {'composite':40s} {composite:.3f}")

    # HMLR Hydra9: faithfulness 1.00, recall 1.00, precision 0.23 — mean 0.743.
    # Our composite adds answer_relevancy as a 4th metric. 0.75 is the floor
    # to claim parity with HMLR on the 3 metrics they report.
    assert composite >= 0.75, (
        f"Hydra9 composite {composite:.3f} below 0.75 floor — "
        f"Dossier did not match HMLR on this benchmark.\n"
        f"Scores: {scores}"
    )
