#!/usr/bin/env python
"""Run the RAGAS RAG evaluation end-to-end as a script.

Usage:
    pip install -e ".[eval,hmlr]"
    export OPENAI_API_KEY=sk-...
    python scripts/run_ragas_bench.py

Optionally:
    python scripts/run_ragas_bench.py --size 10 --out /tmp/ragas.csv

This is the same flow as ``tests/bench/test_ragas_rag.py`` without the
pytest gate — useful for one-off runs where you want the full console
report instead of an assertion.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "bench" / "fixtures" / "raw"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=6, help="Testset size (default: 6)")
    parser.add_argument("--eval-model", default="gpt-4o", help="RAGAS evaluator model")
    parser.add_argument("--answer-model", default="gpt-4.1-mini", help="Answer model")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "ragas_report.csv")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    # late imports so --help stays cheap
    import openai
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import OpenAIEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )
    from ragas.testset import TestsetGenerator

    from dossier.config import DossierConfig
    from dossier.ingest import ingest_document
    from dossier.query import query

    print(f"loading fixtures from {args.fixtures} ...")
    loader = DirectoryLoader(
        str(args.fixtures),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    if not docs:
        print(f"error: no markdown files in {args.fixtures}", file=sys.stderr)
        return 2
    print(f"  loaded {len(docs)} docs")

    print(f"bootstrapping Dossier project + ingesting sources ...")
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="dossier_ragas_"))
    cfg = DossierConfig.for_root(tmp)
    cfg.ensure_dirs()
    for src in args.fixtures.glob("*.md"):
        (cfg.raw_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    for src in cfg.raw_dir.glob("*.md"):
        ingest_document(src, cfg=cfg)
    print(f"  project at {cfg.root}")

    print(f"building RAGAS LLM wrappers ({args.eval_model} eval, {args.answer_model} answer) ...")
    evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model=args.eval_model, temperature=0))
    evaluator_embeddings = OpenAIEmbeddings(client=openai.OpenAI())
    answer_llm = ChatOpenAI(model=args.answer_model, temperature=0)

    print(f"generating testset (size={args.size}) ...")
    gen = TestsetGenerator(llm=evaluator_llm, embedding_model=evaluator_embeddings)
    testset = gen.generate_with_langchain_docs(docs, testset_size=args.size)
    print(f"  got {len(testset.to_pandas())} samples")

    print("running Dossier query + answering each ...")
    samples = []
    for row in testset.to_pandas().to_dict(orient="records"):
        q = row["user_input"]
        result = query(q, cfg=cfg, limit=8)
        contexts = [f"[{c.kind}:{c.ref}] {c.text}" for c in result.candidates]
        answer = answer_llm.invoke(result.hydrated.prompt)
        samples.append(
            {
                "user_input": q,
                "retrieved_contexts": contexts,
                "response": answer.content if hasattr(answer, "content") else str(answer),
                "reference": row.get("reference") or row.get("ground_truth") or "",
            }
        )

    print("evaluating with RAGAS ...")
    dataset = EvaluationDataset.from_list(samples)
    report = evaluate(
        dataset=dataset,
        metrics=[
            ContextRecall(),
            ContextPrecisionWithReference(),
            Faithfulness(),
            AnswerRelevancy(),
        ],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )
    df = report.to_pandas()
    df.to_csv(args.out, index=False)
    print(f"\nreport written to {args.out}")
    print(df.to_string())
    print("\nmean scores:")
    for col in df.columns:
        if df[col].dtype.kind == "f":
            print(f"  {col:40s} {df[col].mean():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
