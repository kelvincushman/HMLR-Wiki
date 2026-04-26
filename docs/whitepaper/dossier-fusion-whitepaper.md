# Dossier: A Wiki-Backed Memory System That Matches HMLR on Hydra9 Hard Mode

**Author:** Kelvin Lee
**Date:** 2026-04-25
**Version:** 1.0
**License:** MIT

---

## Abstract

We introduce **Dossier**, a memory system for LLM agents that fuses Sean VanWinkle's HMLR (Hierarchical Memory with Lattice Retrieval) state engine with Andrej Karpathy's LLM Wiki pattern. The thesis: HMLR's `DossierStorage` and Karpathy's wiki pages are the same abstraction — a compiled, persistent summary that updates rather than re-derives — applied to different input streams. By swapping HMLR's SQL-blob output for human-readable markdown wiki pages, we obtain a memory system that is git-diffable, Obsidian-compatible, editable by humans, and structurally identical to HMLR for retrieval purposes.

We evaluate Dossier on a document-ingest variant of HMLR's Hydra9 Hard Mode benchmark. After sixteen labelled experiments using a Karpathy-style autoresearch loop, the final pipeline (exp-P) ties HMLR on faithfulness (1.000) and context recall (1.000), exceeds it on precision (0.938 vs 0.23), and beats the published 3-metric mean by **+0.236** (0.979 vs 0.743). Every metric is RAGAS-judged with the same evaluator stack HMLR uses.

This document records the architecture, methods, the autoresearch experimental loop, the per-experiment results, and the reproducibility recipe. Every result is reproducible with the harness, fixture corpus, and pipeline code released alongside.

## 1. Introduction

### 1.1 Problem statement

Two recent agent-memory ideas attack the same underlying problem from opposite ends.

**HMLR** addresses *conversational state*. Across many sessions, how does an agent retain, retrieve, and reason about facts that were introduced turns or days ago? HMLR's published verification on Hydra9 Hard Mode — 21 isolated messages spread over 30 simulated days, no conversation history visible at inference, 100% context reconstruction from long-term memory — is to our knowledge the strongest published result on this kind of test.

**The LLM Wiki pattern** addresses *document-derived knowledge*. How does an agent compile what it has read once into a persistent artifact that can be queried forever, instead of re-deriving from raw sources every turn? Karpathy's gist proposes a three-layer architecture (`raw/`, `wiki/`, `CLAUDE.md` schema) and three operations (ingest, query, lint), but explicitly leaves the engine open.

The two systems target different failure modes — dialogue memory loss vs. RAG repeat-discovery — but the underlying abstraction is shared. HMLR's `DossierStorage` is a "persistent cross-topic, cross-day artifact designed to reconstruct causal chains from long-buried information." Karpathy's wiki page is "the compiled artifact that gets updated incrementally rather than re-derived." Both are compiled summaries that compound.

### 1.2 The fusion claim

Our claim is structural: **the input to that compiled summary doesn't matter**. Whether the new evidence is a dialogue turn (HMLR's input) or a document chunk (Karpathy's input), the engine should write to the same compiled artifact in the same way. Swap markdown for SQL blobs and you get human readability for free; keep the engine and you keep HMLR's verified guarantees.

This document tests that claim head-to-head against HMLR's own hardest published benchmark.

### 1.3 Related work

- **HMLR** (Sean VanWinkle, MIT-licensed, ~375 GitHub stars). Public benchmarks include Hydra9 Hard Mode (composite metric reported as faithfulness 1.00, recall 1.00, precision 0.23) and earlier RAGAS-verified scenarios covering API key rotation, user-invariant enforcement, temporal ordering, policy deprecation, and zero-keyword recall. Tested only on `gpt-4.1-mini`.
- **LLM Wiki pattern** (Andrej Karpathy, public gist, 5,000+ stars). Three-layer architecture; explicit operations for ingest, query, and lint. Community extensions (rohitg00's *agentmemory*, jgravelle's *jDocMunch*, Headkey, Timeln, Nebula) reinvent memory primitives without integrating HMLR.
- **autoresearch** (Andrej Karpathy). One-file-per-agent iteration loop adapted in this work as an experimental discipline rather than a training methodology.
- **RAGAS** (Vibrant Labs). The evaluator framework HMLR's published numbers cite; the same harness we use here.

## 2. Architecture

Dossier's directory layout mirrors Karpathy's gist exactly:

```
dossier/
├── raw/                    # immutable source documents
├── wiki/                   # LLM-maintained markdown
│   ├── index.md            # auto-regenerated content catalog
│   ├── log.md              # append-only activity log
│   ├── entities/           # one page per person/org/product/system
│   ├── concepts/           # one page per idea/policy/constraint
│   └── sources/            # one summary page per file in raw/
├── .hmlr/                  # engine internals (gitignored contents)
│   ├── facts.db            # SQLite key-value fact store
│   ├── embeddings/         # vector index
│   └── bridge_blocks.json  # active-topic short-term cache
├── src/dossier/            # the Python package
└── autoresearch/
    ├── memory.py           # the single file under iterative experimentation
    ├── run_experiment.py   # fixed harness
    ├── log.jsonl           # append-only experiment log
    └── program.md          # agent instructions
```

Wiki pages are markdown with YAML frontmatter carrying HMLR-style metadata:

```yaml
---
kind: entity
name: Tartarus-v3
aliases: [Charon, River-9, Styx, K-12, Aether, Phoenix, Legacy-Phi]
confidence: high
last_updated: 2025-04-30
sources:
  - raw: "2025-04-01_tartarus_v3_canonical.md"
supersedes: []
edited_by: llm
---
```

The fact store keeps fast-changing key-value state in SQLite. Wiki pages reference fact-store rows by key rather than duplicating the values.

## 3. Pipeline

The agent owns three Python functions in `autoresearch/memory.py`. Their public API:

```python
def ingest(source_path: Path, cfg: DossierConfig) -> dict[str, Any]:
    """Chunk the source, extract entities/concepts/facts, write wiki pages."""

def consolidate(cfg: DossierConfig) -> dict[str, Any]:
    """Wiki-side synthesis pass — rewrite multi-source pages as coherent dossiers."""

def retrieve(question: str, cfg: DossierConfig, limit: int = 8) -> list[dict[str, Any]]:
    """Return ranked context rows with {ref, kind, text}."""

def synthesize(answer: str, contexts: list[dict[str, Any]], question: str) -> str:
    """Sentence-level grounding filter on a generated answer."""
```

### 3.1 Ingest

For every file dropped into `raw/`:

1. **Chunk** the source by paragraph (target ~1200 chars per chunk).
2. **Extract entities and concepts** via one structured-output LLM call. The extractor is prompted to (a) skip junk like pronouns and bare sentence-start capitalisations, (b) resolve aliases where text supports it, (c) produce a one-sentence summary plus evidence snippets per entity/concept.
3. **Extract facts** via a second structured-output LLM call producing `(subject, predicate, value, evidence, date)` rows.
4. **Write wiki pages** via the contradiction-resolution policy in `wiki_writer.py`: newer source wins by default; `confidence: high` overrides older claims; ties flag `[[REVIEW]]` and do not silently overwrite.
5. **Write a source-summary page** at `wiki/sources/<date>_<slug>.md` listing the entities, concepts, and facts extracted from this file plus a lead summary.
6. **Append one entry** to `log.md`.

The two LLM extractor prompts are reproduced in §6 below.

### 3.2 Consolidate (Gardener-style synthesis)

After all ingests complete, `consolidate()` walks every entity and concept page touched by three or more sources. For each, it loads (a) the existing page body, (b) the source-summary page bodies for each source reference, and (c) all fact-store rows whose subject matches the page name.

It then asks the LLM to rewrite the page body as a single coherent dossier under explicit listing rules:

- Every named alias must appear verbatim (no "and several earlier names" collapses).
- Every version number / policy revision must appear verbatim with a one-line description.
- Every quantitative claim must appear verbatim ("400,000 records/day", "4.7 million", etc.).
- Adversarial qualifiers (`rogue`, `unauthorised`, `revoked by footnote`) must be preserved word-for-word.
- Current vs superseded must be marked with `currently active` / `SUPERSEDED` / `REVOKED`.
- Every non-trivial claim must cite the source filename in `[brackets]`.
- Output is markdown only — no frontmatter, no code fences, no preamble.

The rewritten body replaces the prior body on disk. Frontmatter (sources, supersedes, last_updated) is preserved.

### 3.3 Retrieve

`retrieve(question, cfg, limit=8)` runs a multi-stage funnel:

1. **Wide retrieval**. If the question looks multi-hop (heuristic gate: contains "and", temporal keywords, or three-plus named entities) and embedding retrieval is on, the LLM first decomposes the question into two sub-queries; each sub-query plus the original is embedded; cosine similarity is scored against every wiki page and every fact-store row; top-4 per query are unioned and the result reranked against the original question. Otherwise straight cosine retrieval at width `limit × 3`.
2. **Hybrid rerank**. The wide candidate set is scored by a weighted sum: 0.65 × embedding cosine + 0.20 × token-overlap (BM25-lite) + 0.15 × exact fact-key match. Top-12 survive.
3. **LLM rerank**. A single LLM call ranks those 12 by relevance to the question and keeps the top-8.
4. **Raw-source floor**. Of the eight final slots, four are reserved for source-summary pages by direct embedding similarity (excluding refs already in the main set). This guarantees verbatim claim language survives even when the LLM rerank prefers consolidated entity pages.

Step 4 was the recall-recovery insight in exp-M. Without it, recall on Hydra9 was 0.600; with it, recall is 1.000.

### 3.4 Synthesize

`synthesize()` is a faithfulness filter applied after the answer LLM produces a draft. The current rule set (exp-P):

1. Split the draft into sentences.
2. For each sentence, verify it is *directly* supported by some context block — light paraphrase OK, extrapolation not OK.
3. If supported, keep the sentence verbatim (no rewrite).
4. If unsupported, drop entirely. On uncertainty, drop.
5. Output is natural-language prose with no inline citation tags (those broke RAGAS's `answer_relevancy` metric in two prior experiments by making the output unparseable).

## 4. Methods

### 4.1 The autoresearch experimental loop

Karpathy's autoresearch repository describes an agent-driven ML research setup: one file the agent edits (`train.py`), one metric to maximise (validation bits-per-byte), a five-minute training budget, ~12 experiments per hour. The same pattern transfers to memory pipelines. We adapted it as follows:

- **One file under iteration**: `autoresearch/memory.py`. The agent edits this only.
- **Fixed harness**: `autoresearch/run_experiment.py`. Bootstraps a fresh project, ingests the fixture corpus through the current `memory.py`, runs the eval set, scores with RAGAS, appends one row to `log.jsonl`.
- **Metric**: RAGAS composite (mean of context_recall, llm_context_precision_with_reference, faithfulness, answer_relevancy).
- **Budget**: ~3 minutes wall clock and ~$0.30 OpenAI API cost per experiment.
- **Discipline**: every experiment logs its toggle state, ingest counts, wall time, and per-metric scores. Reverts are kept in the log as negative results for future agents.

### 4.2 Evaluation corpora

We used two corpora:

**Hard corpus** (~7 markdown files, 11 hand-crafted eval pairs). Designed to exercise multi-hop retrieval, temporal supersession, and factoid recall in roughly equal mix. Lives at `tests/bench/fixtures/raw/`.

**Hydra9 doc-variant** (21 dated markdown files spanning ~30 simulated days, 1 final compliance query with reference answer). Mirrors HMLR's published Hydra9 Hard Mode example: 8-hop entity-alias drift, 8-step policy cascade including draft-ignored, footnote-revoked, and rogue-authored revert dynamics, plus distractors. Lives at `tests/bench/fixtures/hydra9_docvariant/__init__.py` (single Python module containing all 21 docs as data).

### 4.3 Models

Same answer model HMLR is verified on: `openai/gpt-4.1-mini`, accessed via OpenRouter (most OpenAI projects don't have direct 4.1-mini access). Temperature 0.

RAGAS evaluator: `gpt-4o-mini` with `text-embedding-3-small`. Same evaluator stack we use throughout — score comparability is paramount.

### 4.4 Component switchboard

Eight toggles in `memory.py`:

```python
USE_LLM_EXTRACTORS = True       # LLM entity/concept/fact extraction (exp-A)
USE_EMBEDDING_RETRIEVAL = True  # cosine over wiki + fact store (exp-B)
USE_QUERY_DECOMPOSITION = True  # gated multi-hop sub-queries (exp-E)
USE_HYBRID_RERANK = True        # embed + token + fact-exact weighted sum (exp-F)
USE_LLM_RERANK = True           # gentle final cut on survivors (exp-I/J)
USE_WIKI_SYNTHESIS = True       # Gardener-style page consolidation (exp-L)
USE_RAW_SOURCE_FLOOR = True     # 4 reserved retrieval slots for raw sources (exp-M)
USE_LLM_SYNTHESIS = True        # sentence-level grounding filter (exp-P)
```

Each toggle was introduced in the experiment indicated and remains on in the final pipeline.

## 5. Results

### 5.1 Hard-corpus journey (sessions 1-2)

| # | upgrade | composite | Δ baseline | recall | precision | faithfulness | relevancy |
|---|---|---|---|---|---|---|---|
| — | heuristic baseline | **0.710** | — | 0.727 | 0.700 | 0.751 | 0.663 |
| A | LLM extractors | 0.810 | +0.100 | 0.712 | 0.699 | 0.987 | 0.840 |
| B | + embedding retrieval | 0.841 | +0.131 | 0.818 | 0.762 | 0.867 | 0.918 |
| C | + LLM synthesis pass | 0.867 | +0.157 | 0.833 | 0.779 | 0.942 | 0.916 |
| D | + aggressive decomposition ❌ | 0.862 | +0.152 | 0.864 | 0.732 | 0.942 | 0.911 |
| E | + gated decomposition | 0.906 | +0.196 | 0.924 | 0.802 | **1.000** | 0.900 |
| F | + hybrid rerank | 0.921 | +0.211 | 0.864 | 0.916 | 0.982 | **0.924** |
| G | + entity-centric boost ❌ | 0.912 | +0.202 | 0.864 | 0.909 | 0.970 | 0.907 |
| H | hybrid weights tweak ❌ | 0.908 | +0.198 | 0.909 | 0.864 | 0.955 | 0.906 |
| I | + LLM rerank | 0.921 | +0.211 | 0.833 | 0.946 | 0.982 | 0.922 |
| **J** | **+ deeper funnel (24→12→8)** | **0.923** | **+0.213** | 0.833 | **0.965** | 0.970 | 0.923 |
| K | wider output ❌ | 0.907 | +0.197 | 0.909 | 0.913 | 0.909 | 0.897 |

❌ = regressed; reverted. exp-J locked in as session-2 winner.

### 5.2 Hydra9 progression (session 3)

| stage | composite | faithfulness | recall | precision | what changed |
|---|---|---|---|---|---|
| starting (exp-J → Hydra9) | 0.729 | 0.533 | 0.600 | 1.000 | exp-J pipeline applied directly |
| + wiki synthesis (exp-L) | 0.836 | 1.000 | 0.600 | 1.000 | Gardener-style page consolidation |
| + verbatim listing + raw-source floor (exp-M) | 0.916 | 0.900 | **1.000** | 0.962 | strict prompt + reserved retrieval slots |
| **+ strict prose-only filter (exp-P)** | **0.925** | **1.000** | **1.000** | 0.938 | sentence-level grounding |

### 5.3 Head-to-head with HMLR on Hydra9

HMLR's published Hydra9 figures (from their README, RAGAS-verified, LangSmith traces public):

| Metric | HMLR Hydra9 | **Dossier exp-P** |
|---|---|---|
| Faithfulness | 1.00 | **1.000** |
| Context Recall | 1.00 | **1.000** |
| Precision | 0.23 | **0.938** |
| 3-metric mean | 0.743 | **0.979** |
| Answer relevancy | (not reported) | 0.762 |
| 4-metric composite | (not reported) | 0.925 |

**Dossier matches HMLR on faithfulness and context recall, exceeds it on precision by +0.708, and beats the 3-metric mean by +0.236.**

### 5.4 Caveats

- The Hydra9 doc-variant is a parallel scenario built from HMLR's *published* example. We did not have access to HMLR's exact internal Hydra9 corpus (their full test harness is in their repo but the published metrics cite the example we mirrored).
- HMLR's published numbers are from a single run on `gpt-4.1-mini`; LLMs are not fully deterministic at temperature 0. We re-ran our Hydra9 result three times during development; per-metric variance was ±0.05 across runs, never enough to flip the headline comparison.
- The hard-corpus composite dipped 0.902 → 0.870 between exp-M and exp-P. This is the cost of the strict synthesis filter on simpler factoid questions where natural paraphrase would otherwise be acceptable. A future experiment could add per-question-type routing.
- We tested only the document-ingest variant of Hydra9. HMLR's other published scenarios (Vegetarian Trap, 30-Day Deprecation, 50-Turn Long Conversation) have not been ported. The Hydra9 result is one data point — the hardest one HMLR reports, but still one point.

## 6. Code references

The complete pipeline is `autoresearch/memory.py` (~600 lines). Key prompts:

### 6.1 LLM entity + concept extractor

```text
Extract entities and concepts from the text below.

ENTITIES are named people, organisations, products, locations, or systems.
Each entity gets one record. Resolve pronouns to names where possible.
Skip junk like "The", "She", bare sentence-start capitalisations.

CONCEPTS are recurring ideas, policies, constraints, invariants, or
frameworks. Each concept gets one record.

Return ONLY a single JSON object, no prose, with this shape:
{"entities": [{"name": "...", "aliases": [...], "summary": "...",
               "evidence": ["snippet"]}, ...],
 "concepts": [{"name": "...", "summary": "...", "evidence": ["snippet"]}, ...]}
```

### 6.2 LLM fact extractor

```text
Extract atomic factual claims from the text. Each claim is one row.

Rules:
- Subject = named entity (person, org, product). No pronouns.
- Predicate = short verb phrase: "is", "reports to", "is based in", ...
- Value = the object of the claim, concise.
- Evidence = the exact source sentence.
- Date = ISO date if the claim has a time anchor in the text, else null.

Return JSON: {"facts": [{"subject":..., "predicate":..., "value":...,
              "evidence":..., "date":...}]}
```

### 6.3 Wiki-side consolidation (exp-L, tightened in exp-M)

```text
Rewrite the wiki page for {entity_name} as one coherent dossier.

STRICT REQUIREMENTS — recall depends on these:
1. List every named alias / former name verbatim.
2. List every version / policy number / revision verbatim.
3. Preserve every quantitative claim verbatim.
4. Mark current vs. superseded explicitly.
5. Preserve adversarial qualifiers ('rogue', 'unauthorised', etc.).
6. State the CURRENT canonical state first.
7. Cite the source filename for every non-trivial claim.
8. Return ONLY markdown for the page body.
```

### 6.4 Synthesis filter (exp-P)

```text
You are a faithfulness filter. Apply these rules strictly:

1. Split the draft into individual sentences.
2. For each sentence, decide whether some context block DIRECTLY supports
   the claim. Light paraphrase OK; extrapolation not OK.
3. If supported: keep the sentence verbatim. Do not modify.
4. If NOT supported: drop entirely. When in doubt, drop.
5. Do not add any sentence not in the draft.
6. Preserve original sentence order; preserve verdict words verbatim.
7. Output natural-language prose, no inline citation tags, no headings.
```

### 6.5 Hybrid rerank scoring

```python
combined = (HYBRID_W_EMBED * cosine(question, candidate)         # 0.65
          + HYBRID_W_TOKEN * token_overlap_score(question, candidate)  # 0.20
          + HYBRID_W_FACT  * (1.0 if exact_fact_match else 0.0)) # 0.15
```

## 7. Reproducibility

```bash
# clone + install
git clone https://github.com/kelvincushman/HMLR-WIKI
cd HMLR-WIKI/dossier
pip install -e ".[eval]"

# credentials — judge + embeddings on OpenAI; answer model on OpenRouter
export OPENAI_API_KEY=sk-...
export DOSSIER_ANSWER_API_KEY=sk-or-v1-...
export DOSSIER_ANSWER_BASE_URL=https://openrouter.ai/api/v1
export DOSSIER_BENCH_ANSWER_MODEL=openai/gpt-4.1-mini

# headline benchmark — Hydra9 doc-variant
pytest tests/bench/test_hydra9_docvariant.py --run-bench -s -v

# hard-corpus regression bench
pytest tests/bench/test_ragas_rag.py --run-bench -s -v

# single autoresearch run (current memory.py config)
python autoresearch/run_experiment.py
```

Each Hydra9 run takes ~5 minutes wall clock and costs ~$0.50-0.80 in API usage. Hard-corpus runs are ~3 minutes and ~$0.30. Results append to `dossier/autoresearch/log.jsonl`.

## 8. Discussion

### 8.1 What worked

The component classes that produced material gains:

1. **LLM extractors** at ingest time. Replaced regex SVO detection with structured-output LLM calls. +0.100 composite alone (heuristic baseline → exp-A). The wiki pages produced by regex extractors were noisy junk ("She", "The", "Python" listed as entities); LLM-produced pages contain real summaries and clean evidence.
2. **Embedding retrieval over the lattice**. Token overlap loses semantic matches; cosine over OpenAI embeddings catches them. +0.031 composite (exp-A → exp-B).
3. **Gated query decomposition**. Aggressive decomposition (3 sub-queries) regressed. Heuristic-gated decomposition (only on multi-hop questions, 2 sub-queries) gained +0.039. The gate was the unlock — decomposition is essential for some questions and actively harmful on others.
4. **Wiki-side synthesis**. The single biggest gain on Hydra9 — composite 0.729 → 0.836 (+0.107). The previously-stubbed Karpathy half of the fusion. Demonstrated empirically that the compiled-artifact abstraction is the load-bearing claim.
5. **Strict synthesis with raw-source floor**. Closed the recall gap (0.60 → 1.00 on Hydra9). The verbatim retrieval slots survived rerank; the strict filter then verified faithfulness.

### 8.2 What didn't work

Five experiments regressed and were reverted:

- **Strict per-sentence citation** (exp-2 in session 1). The post-process stripped too many sentences when their inline `[tag]` format didn't match the regex.
- **Aggressive query decomposition** (exp-D). 3 sub-queries × 6 candidates each created a noisy union the rerank couldn't recover from.
- **Entity-centric boost** (exp-G). Pulling all facts/pages about question-mentioned entities sounded right but the hybrid rerank was already finding them.
- **Heavy-token hybrid weights** (exp-H). Shifting from 0.65/0.20 to 0.50/0.35 traded precision for recall at a worse rate.
- **Wider output** (exp-K). Adding two more retrieval slots let marginal content back in.

The autoresearch loop's discipline — log every run including reverts — made these dead ends visible to future iteration.

### 8.3 The bounded recall trade-off

HMLR's recall on Hydra9 is 1.000 because their architecture stores claims verbatim in SQL; retrieval is a database lookup. Dossier's wiki synthesis paraphrases. We pay the recall tax twice: once at synthesis (paraphrased dossier text) and once at retrieval (rerank may prefer the paraphrased page). Our raw-source-floor trick (4 reserved retrieval slots that bypass rerank) brings recall back to parity, but at a small precision cost.

This is a real trade-off, not a bug. Karpathy's wiki value-add — human readability, editability, git-diffability — depends on synthesis. A pure verbatim store would lose those properties.

### 8.4 Future work

- **Per-question-type routing**. The strict synthesis filter is over-zealous on simple factoid questions. A cheap classifier could route "factoid" vs "multi-hop adversarial" to different synthesis strictness levels.
- **Other HMLR scenarios**. Vegetarian Trap (user-invariant + prompt injection), 30-Day Deprecation, 50-Turn Long Conversation. The Hydra9 result is one point.
- **Relationship-triple graph**. Store extracted facts as `(subject, predicate, object)` triples in a real graph store (Neo4j, kuzudb). Multi-hop retrieval becomes graph traversal rather than vector union.
- **Larger corpora**. Both our test corpora are small (≤21 docs). Karpathy's `index.md` is known to break at ~200 entries; we haven't tested whether our pipeline degrades gracefully past that scale.

## 9. Credits

**Built by Kelvin Lee.**

This work would not exist without:

- **Sean VanWinkle** — author of [HMLR](https://github.com/Sean-V-Dev/HMLR-Agentic-AI-Memory-System), the engine and the benchmarks. The Hydra9 Hard Mode test is the closest thing to a settled answer in agent memory.
- **Andrej Karpathy** — author of the [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [autoresearch](https://github.com/karpathy/autoresearch). The architectural shape and the experimental loop pattern.

Neither author endorsed the merge. The fusion, the experiments, and any errors are mine.

## License

MIT.

## Appendix A — log.jsonl row format

Every experiment run appends one JSON row:

```json
{
  "ts": "2026-04-25T12:34:56+00:00",
  "experiment_note": "exp-P. Strict drop, natural-language output...",
  "eval_model": "gpt-4o-mini",
  "answer_model": "openai/gpt-4.1-mini",
  "answer_provider": "https://openrouter.ai/api/v1",
  "toggles": {
    "USE_LLM_EXTRACTORS": true,
    "USE_EMBEDDING_RETRIEVAL": true,
    "USE_QUERY_DECOMPOSITION": true,
    "USE_HYBRID_RERANK": true,
    "USE_LLM_RERANK": true,
    "USE_WIKI_SYNTHESIS": true,
    "USE_RAW_SOURCE_FLOOR": true,
    "USE_LLM_SYNTHESIS": true
  },
  "ingest_totals": {"entities": 28, "concepts": 6, "facts": 31},
  "consolidate": {"consolidated": 5, "skipped": 14},
  "wall_seconds": 185.9,
  "composite": 0.870,
  "scores": {
    "context_recall": 0.924,
    "llm_context_precision_with_reference": 0.839,
    "faithfulness": 0.829,
    "answer_relevancy": 0.888
  },
  "n_samples": 11
}
```

## Appendix B — corpus design notes

The Hydra9 doc-variant corpus is constructed to mirror HMLR's published Hydra9 Hard Mode example without copying it verbatim. The eight-name alias chain and eight-step policy cascade are the same shape; the project, names, and specific numbers are paraphrased. The intent is parity with HMLR's test architecture, not reproduction of HMLR's IP. All 21 docs and the final reference answer are in `tests/bench/fixtures/hydra9_docvariant/__init__.py` for full transparency.

## Appendix C — what we did not measure

- **Latency**. Our pipeline runs ~3-5 minutes per Hydra9 evaluation. HMLR doesn't publish latency. Production deployment would care; this paper does not.
- **Cost per query** (production). Wiki synthesis is amortised — one consolidation pass per ingest, one filter pass per query. Per-query cost is dominated by the answer generation + synthesis filter (~$0.05-0.10 on `gpt-4.1-mini`).
- **Multi-user / concurrent ingest**. Out of scope.
- **Adversarial robustness** beyond Hydra9's published trap (the rogue v7 / v8 revert dynamic). Real prompt-injection testing was not run.
