# HMLR — overview

HMLR (Hierarchical Memory with Lattice Retrieval) is a Python library for AI
agent memory built by Sean VanWinkle. It is licensed under MIT.

## Architecture

HMLR combines a bridge-block mechanism for topic segmentation with a fact
extraction pipeline and hierarchical retrieval that operates at the
sentence, paragraph, and block levels. The package has been tested only
against GPT-4.1-mini; other models may produce incorrect results.

## Components

- **Governor** — routes each message either to an existing bridge block
  (active topic) or to a new one (new topic).
- **Scribe** — maintains a structured user profile by extracting
  preferences, constraints, and invariants from dialogue turns.
- **FactScrubber** — extracts atomic key-value facts into a SQL fact
  store, overwriting older values on temporal update.
- **LatticeCrawler** — performs vector search over the memory corpus.
- **DossierStorage** — persistent cross-topic artifacts designed to
  reconstruct causal chains from long-buried information.
- **Gardener** — a batch process that promotes short-term memories
  (bridge blocks) into long-term storage.

## Verification

HMLR has been verified on Hydra9 Hard Mode: 21 isolated messages spread
over 30 simulated days, with no conversation history at inference time,
achieving 100 percent context reconstruction from long-term memory alone.
Earlier RAGAS-verified benchmarks cover API key rotation, user-invariant
enforcement, temporal ordering, policy deprecation, and zero-keyword recall.
