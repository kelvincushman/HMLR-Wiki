# autoresearch — Dossier query-strategy iteration

Pattern borrowed from Karpathy's [autoresearch](https://github.com/karpathy/autoresearch):
one file the agent edits, one metric to maximise, fixed test corpus, autonomous loop.

## What's different from Karpathy's autoresearch

| Karpathy's autoresearch | this |
|---|---|
| Trains a small GPT on 5-min budget | Evaluates a RAG strategy |
| Metric: `val_bpb` (training loss) | Metric: RAGAS composite (retrieval + generation) |
| File under iteration: `train.py` (model, optimizer, loop) | File under iteration: `strategy.py` (retrieve, build_prompt, post_process) |
| Budget: wall clock, GPU time | Budget: wall clock + API spend |
| Runs on: single H100 | Runs on: CPU + OpenAI API |

The point of the pattern is the same: **the human edits `program.md`, the
agent edits the one file, the harness keeps score.**

## Files

- `program.md` — agent instructions (the "research org code"). Edit this when
  you want to change how the agent approaches iteration.
- `strategy.py` — the one file the agent edits. Defines three functions:
  `retrieve(question, cfg) -> rows`, `build_prompt(question, rows) -> prompt`,
  `post_process(answer, question, rows) -> answer`.
- `run_experiment.py` — fixed harness. Reads `strategy.py`, runs the 6 eval
  pairs from the RAGAS bench, logs one row to `log.jsonl`.
- `log.jsonl` — append-only experiment log. One JSON row per run.

## Running

```bash
cd dossier
pip install -e ".[eval]"
export OPENAI_API_KEY=sk-...

# one-off
python autoresearch/run_experiment.py

# agent loop — point Claude Code at program.md and let it iterate
claude -f autoresearch/program.md
```

Each run costs about $0.05-0.15 and takes 60-120 seconds wall clock. The
`log.jsonl` prints the delta to the best composite so far, so the agent can
decide to keep or revert between runs.

## Scoring

The composite is the simple mean of the four RAGAS metrics:

```
composite = mean(context_recall,
                 llm_context_precision_with_reference,
                 faithfulness,
                 answer_relevancy)
```

Baseline on gpt-4o-mini (2026-04-24): **composite ≈ 0.77**. The agent's job
is to find strategy edits that push this up.

## How this relates to the HMLR benchmark

HMLR's published claim is "100% context reconstruction on Hydra9 Hard Mode"
— a specific test with 21 messages over 30 simulated days, verified on
gpt-4.1-mini. That's a different benchmark than this one: different corpus,
different answer model (our project doesn't currently have 4.1-mini access),
different notion of "score".

What this harness does is give Dossier a *reproducible, self-comparable* way
to measure query quality and iterate on it — the same engineering discipline
Karpathy applied to small-model training, pointed at our problem instead.
Proving Dossier beats HMLR's published numbers requires running Dossier
against the Hydra9 corpus on gpt-4.1-mini. That's a separate and much larger
piece of work (it's what `tests/bench/test_hydra9_docvariant.py` is a stub
for).
