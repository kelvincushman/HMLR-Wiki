# HMLR-WIKI / Dossier

> A wiki-backed memory system that matches HMLR on Hydra9 Hard Mode.

**Built by Kelvin Lee.** Built on top of [HMLR](https://github.com/Sean-V-Dev/HMLR-Agentic-AI-Memory-System) by Sean VanWinkle and the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy.

---

## TL;DR

Dossier is a memory system for LLM agents. It fuses two ideas:

- **HMLR** — a state engine for dialogue memory, RAGAS-verified, perfect on Hydra9 Hard Mode
- **LLM Wiki** — a markdown-based knowledge layer that compiles raw sources once and queries the compiled artifact forever

The fusion claim: HMLR's `DossierStorage` and Karpathy's wiki pages are the same abstraction applied to different input streams. Swap the input, keep the engine, and you get a human-readable, git-diffable, Obsidian-compatible memory system with HMLR's verified guarantees.

The result: on HMLR's own Hydra9 Hard Mode benchmark, Dossier matches HMLR on faithfulness (1.000) and recall (1.000), exceeds it on precision (0.938 vs 0.23), and beats the published 3-metric mean by **+0.236**.

| Metric | HMLR Hydra9 | **Dossier** |
|---|---|---|
| Faithfulness | 1.00 | **1.000** |
| Context Recall | 1.00 | **1.000** |
| Precision | 0.23 | **0.938** |
| 3-metric mean | 0.743 | **0.979** |

Full results, methods, and reproducibility recipe in [docs/whitepaper/dossier-fusion-whitepaper.md](docs/whitepaper/dossier-fusion-whitepaper.md).

A more readable narrative version is at [docs/blog/2026-04-25-dossier-beats-hmlr-on-hydra9.md](docs/blog/2026-04-25-dossier-beats-hmlr-on-hydra9.md).

## Repository layout

```
HMLR-WIKI/
├── README.md                          # this file
├── docs/
│   ├── blog/
│   │   └── 2026-04-25-dossier-beats-hmlr-on-hydra9.md   # ~2000-word write-up
│   └── whitepaper/
│       └── dossier-fusion-whitepaper.md                 # full technical paper
├── dossier/                           # the active project
│   ├── README.md                      # project-level docs
│   ├── SCHEMA.md                      # wiki conventions
│   ├── AGENTS.md                      # LLM-facing guide
│   ├── pyproject.toml
│   ├── raw/                           # immutable source documents
│   ├── wiki/                          # LLM-maintained markdown
│   │   ├── index.md
│   │   ├── log.md
│   │   ├── entities/
│   │   ├── concepts/
│   │   └── sources/
│   ├── .hmlr/                         # engine internals (gitignored)
│   ├── src/dossier/                   # the Python package
│   ├── tests/                         # 40 unit tests + bench suite
│   │   └── bench/
│   │       ├── test_ragas_rag.py
│   │       └── test_hydra9_docvariant.py
│   ├── autoresearch/                  # Karpathy-style iteration loop
│   │   ├── memory.py                  # the file under iteration
│   │   ├── run_experiment.py          # fixed harness
│   │   ├── log.jsonl                  # every experiment run
│   │   ├── program.md                 # agent instructions
│   │   ├── RESULTS.md                 # full journey
│   │   └── run_model_matrix.py        # cross-model sweep
│   ├── pi-agent/                      # pi.dev skill package
│   └── scripts/run_ragas_bench.py
└── CLAUDE.md                          # guidance for Claude Code in this repo
```

## Quick start

```bash
git clone https://github.com/kelvincushman/HMLR-WIKI
cd HMLR-WIKI/dossier

# install
pip install -e ".[eval]"

# credentials
export OPENAI_API_KEY=sk-...                           # judge + embeddings
export DOSSIER_ANSWER_API_KEY=sk-or-v1-...             # OpenRouter for answer model
export DOSSIER_ANSWER_BASE_URL=https://openrouter.ai/api/v1
export DOSSIER_BENCH_ANSWER_MODEL=openai/gpt-4.1-mini

# basic usage
python -m dossier doctor                               # sanity check
python -m dossier ingest raw/some_article.md           # add a source
python -m dossier query "what do we know about X?"     # query the wiki
python -m dossier gardener                             # consolidation pass
```

## Reproducing the Hydra9 result

```bash
cd dossier

# full bench (locks the headline result on HMLR's own Hydra9)
pytest tests/bench/test_hydra9_docvariant.py --run-bench -s -v

# session bench on the hard corpus
pytest tests/bench/test_ragas_rag.py --run-bench -s -v

# or run a single autoresearch experiment with the current memory.py config
python autoresearch/run_experiment.py
```

Each Hydra9 run takes ~5 minutes and costs ~$0.50-0.80 in API calls. Results append to `dossier/autoresearch/log.jsonl`.

## Architecture in one paragraph

Dossier wraps three Python functions in `autoresearch/memory.py`. **`ingest(source, cfg)`** chunks a raw file, runs LLM extractors to produce structured entities + concepts + facts, and writes them to wiki pages and the SQLite fact store. **`consolidate(cfg)`** is the Gardener-style synthesis pass — for every multi-source page, the LLM rewrites the body as a single coherent dossier (chronological alias chains, explicit policy supersession, current-state markers). **`retrieve(question, cfg)`** runs a multi-stage funnel: query decomposition (gated to multi-hop questions), embedding retrieval, hybrid rerank (embed + token + fact-exact weighted sum), LLM rerank on survivors, and a raw-source floor that reserves four retrieval slots for source-summary pages. **`synthesize(answer, ...)`** is a sentence-level grounding filter that drops claims unsupported by retrieved context.

That's it. Every successful experiment in the journey replaced one of these components with a smarter version.

## The autoresearch loop

The pipeline above wasn't designed top-down — it was discovered through 16 labelled experiments using a [Karpathy-style autoresearch loop](https://github.com/karpathy/autoresearch) adapted from ML training to memory-pipeline iteration. The agent owns one file (`memory.py`); the harness ingests a fixture corpus, runs the eval set, scores with RAGAS, and appends to `log.jsonl`. Each experiment costs ~$0.30 and takes ~3 minutes.

11 experiments advanced the score; 5 regressed and were reverted. The full journey is in [autoresearch/RESULTS.md](dossier/autoresearch/RESULTS.md).

## Status

- 40/40 unit tests pass
- Hydra9 doc-variant ties HMLR on faithfulness + recall, beats on precision
- Hard corpus composite **0.870** with the strict synthesis pipeline (current locked-in config)
- All experiments reproducible via `pytest --run-bench`

## Credits

**Built by Kelvin Lee.**

Built on:

- [HMLR](https://github.com/Sean-V-Dev/HMLR-Agentic-AI-Memory-System) by Sean VanWinkle — the engine, the benchmarks, the model-choice discipline. Hydra9 Hard Mode is the test that made the comparison meaningful.
- [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy — the architectural shape, schema convention, and the autoresearch loop pattern.

Neither author endorsed this merge. The fusion, the experiments, and any errors are mine.

## License

MIT. See [LICENSE](LICENSE).
