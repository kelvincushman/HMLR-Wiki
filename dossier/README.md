# Dossier

> A dossier for every entity. Maintained by the LLM. Readable by you.

Dossier fuses two recent patterns into one memory system:

- [**HMLR**](https://github.com/Sean-V-Dev/HMLR-Agentic-AI-Memory-System) by Sean VanWinkle — a state engine for dialogue turns (Governor routing, FactScrubber, DossierStorage, Gardener, RAGAS-verified).
- [**LLM Wiki**](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy — a pattern for LLM-maintained markdown that compiles raw sources once and queries the compiled artifact forever.

**The load-bearing claim:** HMLR's `DossierStorage` and Karpathy's wiki pages are the same abstraction — a compiled, persistent summary that updates rather than re-derives. They're just applied to different input streams. Swap the input, keep the engine, and you get a human-readable, git-diffable, Obsidian-compatible wiki with HMLR's temporal-supersession, contradiction-resolution, and multi-hop-reasoning guarantees built in.

## Install

```bash
pip install -e ".[dev]"              # minimum: just the wiki + fact store (stub adapter)
pip install -e ".[hmlr,dev]"         # with real HMLR engine for dialogue
pip install -e ".[all]"              # everything (embeddings, LangGraph, dev)
```

HMLR is an **optional** dep. Without it, `dossier.hmlr_adapter` falls back to a stub so the document-ingest and wiki paths work for the spike in §10 of the spec.

## Quick tour

```bash
# drop a source into raw/ and ingest it
cp ~/Downloads/some_article.md dossier/raw/
dossier ingest raw/some_article.md

# ask the wiki a question (routes through fact store + vector + bridge blocks)
dossier query "what do we know about Alice's dietary constraints?"

# talk to it (requires hmlr extra installed)
dossier chat

# nightly consolidation + lint pass
dossier gardener
```

## Layout

See [SCHEMA.md](SCHEMA.md) for the full convention reference.

```
dossier/
├── raw/            # immutable sources you drop in
├── wiki/           # LLM-maintained markdown (the human-readable lattice)
│   ├── index.md
│   ├── log.md
│   ├── entities/
│   ├── concepts/
│   └── sources/
├── .hmlr/          # SQL fact store, bridge blocks, embeddings
└── src/dossier/    # this package
```

## Status

**Alpha, MVP scaffolding.** The Governor / Scribe / FactScrubber / Gardener modules are wired with real Python interfaces and tests, but they delegate heavy lifting to HMLR when the `hmlr` extra is installed, or to stubs otherwise. Next step: the §10 spike — drop three articles into `raw/`, confirm Scribe writes entity pages, then re-run Hydra9 Hard Mode as a document-ingest variant.

## Evaluation

The RAG pipeline is evaluated with [RAGAS](https://docs.ragas.io/en/stable/getstarted/rag_testset_generation/) — testset generation over the fixture corpus, then four metrics scored against Dossier's retrieved contexts + generated answers: `ContextRecall`, `ContextPrecisionWithReference`, `Faithfulness`, `AnswerRelevancy`.

The bench is gated behind a flag + an API key so it never runs by accident (each run costs real money):

```bash
pip install -e ".[eval]"
export OPENAI_API_KEY=sk-...

# pytest form — asserts score floors, exits non-zero on regression
pytest tests/bench/ --run-bench -k ragas -s

# script form — prints the full report, no assertions
python scripts/run_ragas_bench.py --size 6 --out ragas_report.csv
```

Score floors are deliberately conservative on the first pass (`0.70 / 0.60 / 0.80 / 0.70`). Tighten after 3–5 green runs establish a stable baseline. The fixture corpus lives at [tests/bench/fixtures/raw/](tests/bench/fixtures/raw/) — add or replace documents there to evaluate on your own material.

## Credits

Built on HMLR by Sean VanWinkle and the LLM Wiki pattern by Andrej Karpathy. Neither endorsed this merge — the fusion is my doing. If it breaks, that's on me.

## License

MIT. See [LICENSE](../LICENSE).
