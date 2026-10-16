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

## LLM pipeline

By default the CLI is heuristic and model-free: regex extraction, token-overlap
retrieval, and `query` prints the matching pages and facts rather than an
answer. Set `DOSSIER_PIPELINE=llm` to run `ingest`, `query` and `gardener` on
the benchmarked pipeline in [autoresearch/memory.py](autoresearch/memory.py)
instead:

| command    | `DOSSIER_PIPELINE=llm` behaviour |
|------------|----------------------------------|
| `ingest`   | LLM entity, concept and fact extraction into the same `wiki/` and `.hmlr/facts.db` |
| `query`    | embedding + rerank retrieval, an answer from those contexts only, a grounding filter, then `Sources:` |
| `gardener` | LLM consolidation of pages with 3+ sources, then the usual lint and index pass |
| `doctor`   | also prints the effective model settings |

```bash
pip install -e ".[llm]"        # openai + langchain-openai; no torch
```

| variable | purpose | default |
|----------|---------|---------|
| `DOSSIER_PIPELINE` | `llm` turns the model-backed pipeline on | heuristic |
| `DOSSIER_ANSWER_BASE_URL` | OpenAI-compatible chat endpoint | OpenAI |
| `DOSSIER_ANSWER_API_KEY` | key for that endpoint (falls back to `OPENAI_API_KEY`) | |
| `DOSSIER_BENCH_ANSWER_MODEL` | chat model name | `gpt-4o-mini` |
| `DOSSIER_LLM_EXTRA_BODY` | JSON object sent as the request's `extra_body` | none |
| `DOSSIER_DISABLE_THINKING` | `1` sends `chat_template_kwargs: {"enable_thinking": false}` (Qwen3-style models) | off |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` | embeddings endpoint and key | OpenAI |
| `DOSSIER_EMBED_MODEL` | embedding model name | `text-embedding-3-small` |

A leading `<think>…</think>` block in any model reply is stripped before it is
parsed or written to the wiki, so thinking models work with or without
`DOSSIER_DISABLE_THINKING`.

Example for local vLLM / llama.cpp servers:

```bash
export DOSSIER_PIPELINE=llm
export DOSSIER_ANSWER_BASE_URL=http://127.0.0.1:8097/v1 DOSSIER_ANSWER_API_KEY=local
export DOSSIER_BENCH_ANSWER_MODEL=qwen3.5-27b DOSSIER_DISABLE_THINKING=1
export OPENAI_BASE_URL=http://127.0.0.1:8098/v1 OPENAI_API_KEY=local
export DOSSIER_EMBED_MODEL=qwen3-embedding-8b
```

The benchmark scores in [autoresearch/RESULTS.md](autoresearch/RESULTS.md) are
for OpenAI models; other models are untested until you re-run the bench.

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
