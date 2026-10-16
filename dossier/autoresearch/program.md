# autoresearch — program.md

Agent instructions for improving Dossier's **memory system** via Karpathy's
autoresearch pattern. One file under iteration (`memory.py`), one metric
(RAGAS composite on the hard corpus), one wall-clock budget.

This is not prompt-tuning. This is memory-component replacement: swap
regex extractors for LLMs, swap token overlap for embeddings, add synthesis
passes. Each swap should dramatically move the metric.

## Claude Code model routing

When running this loop in Claude Code, use:

- **Sonnet** for *running* experiments and watching logs. Cheap, fast,
  plenty of headroom for reading tool output. Most of a session is this.
- **Opus Max** for *editing* `memory.py` when you're introducing a real
  component swap (e.g. writing a new LLM prompt, implementing hybrid
  retrieval). That's where thought pays off.

Rough rule: if the next turn is "run `run_experiment.py` and read the
delta", keep Sonnet on. If the next turn is "design a better
`_llm_extract_facts` prompt or refactor the retrieval function", switch to
Opus. Use `/model` in Claude Code to switch.

## The setup

| role | file | who touches |
|------|------|-------------|
| Fixed harness | `run_experiment.py` | don't edit |
| Fixed corpus | `../tests/bench/fixtures/raw/` | add/edit docs only when expanding benchmark |
| Fixed eval pairs | `../tests/bench/test_ragas_rag.py::EVAL_PAIRS` | add/edit only when expanding benchmark |
| **Under test** | **`memory.py`** | **agent edits this — and only this** |
| Log | `log.jsonl` | append-only; the harness writes |

## The metric

Each experiment produces four RAGAS scores:

- `context_recall` — did retrieval surface the claim the reference answer needs?
- `llm_context_precision_with_reference` — how much of retrieval was relevant?
- `faithfulness` — is every claim in the generated answer grounded in the context?
- `answer_relevancy` — does the answer actually address the question?

The composite to maximise is the mean of all four. Baselines:

- Heuristic baseline (regex extractors + token overlap): **0.710**
- Current winner (`memory.py` with all three toggles `True`): **0.867**
- HMLR-verified answer model: `openai/gpt-4.1-mini` (via OpenRouter).

## The loop

1. Read `memory.py`. Understand which toggles are on and what each
   component currently does.
2. Form a hypothesis: which *component* is leaving score on the table?
   Look at the per-metric breakdown in the last `log.jsonl` row —
   faithfulness low means extraction or synthesis needs work; recall low
   means retrieval; relevancy low means the answer model is refusing.
3. Edit `memory.py`: either flip a toggle, or replace a component's body
   with a smarter implementation. Keep the public API stable: the harness
   calls `ingest`, `retrieve`, `synthesize`, `build_prompt`, and the CLI's
   `DOSSIER_PIPELINE=llm` mode (`src/dossier/pipeline.py`) also calls
   `consolidate`, `_get_llm`, `_text` and `_llm_extra_body` and reads
   `LLM_MODEL` / `EMBED_MODEL`. `tests/test_pipeline.py` guards that.
4. Update `EXPERIMENT_NOTE` at the top of `memory.py` to describe what
   you changed and what you expect.
5. Run `python autoresearch/run_experiment.py`. The harness logs one row
   with per-metric scores, the composite, which toggles were on, and how
   many entities/concepts/facts each ingest produced.
6. Compare composite to best so far (printed at end of run). If better,
   keep. If worse, revert or refine.

**Budget:** target 10 experiments per session. Each costs ~$0.10-0.30 and
takes 1-3 minutes wall clock.

## Ideas worth trying

Ordered by estimated impact given current scores:

### Retrieval
- Hybrid scoring: weighted sum of embedding cosine + BM25 + exact-key facts
- Multi-hop retrieval: after initial retrieve, extract named entities
  from top-k, re-retrieve pages about each, union
- Query decomposition: break complex questions into sub-queries, retrieve
  each, merge
- Rerank with a cross-encoder or a cheap LLM "is this relevant? y/n" pass

### Extraction (ingest-time)
- Relationship extraction in addition to facts: "A reports to B",
  "C built D", "E superseded F by G" as first-class graph edges
- Per-claim confidence + date in the extraction prompt, not post-hoc
- Self-consistency: two LLM extraction passes, union entities + take
  higher-confidence facts
- Typed entities: Person, Org, Product, Location, System — so retrieval
  can filter

### Memory structure
- Temporal claim history: store all versions of a fact with timestamps,
  let retrieval choose
- Named-graph facts: `(subject, predicate, object)` triples with a graph
  index, for multi-hop Cypher-style queries
- Page consolidation: Gardener merges near-duplicate entity pages via LLM

### Generation
- Chain-of-thought: ask the answer LLM to plan before answering
- Self-critique: after answering, ask the model to identify any unsupported
  claim and remove it (currently synthesis is this, rough version)
- Citation enforcement: reject any answer where a sentence lacks a
  `[kind:ref]` tag, retry with harsher prompt

## Constraints

- Don't edit the test harness, the corpus, or the eval pairs. Expanding
  the benchmark is a separate decision — open a PR, not a quiet edit.
- Don't switch the answer model mid-loop. `openai/gpt-4.1-mini` is the
  HMLR-verified choice; swapping it changes what the scores mean.
- Don't cache results between experiments. Every run starts with a fresh
  tmp project — your ingest edits must take effect per-run.
- Don't regress composite below 0.80 without a written hypothesis in
  `EXPERIMENT_NOTE` explaining what you're testing.

## Stop conditions

- Composite > 0.92 on the hard corpus: success, write up findings.
- 10 experiments without improvement over current best: stop, summarise
  what was tried.
- Single metric regresses more than 0.10 from current best: revert unless
  the composite improved overall.
