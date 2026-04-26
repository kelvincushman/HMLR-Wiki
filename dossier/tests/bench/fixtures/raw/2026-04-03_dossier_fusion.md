# Dossier — the HMLR + LLM Wiki fusion

Dossier merges HMLR's state engine with Karpathy's LLM Wiki pattern into a
single state-aware, document-aware memory system, authored by Kelvin Cushman.

## The load-bearing claim

HMLR's DossierStorage and Karpathy's wiki pages are the same abstraction
applied to different input streams. Both are compiled, persistent
summaries that get updated incrementally rather than re-derived. Swap the
input and keep the engine, and you get a human-readable, git-diffable,
Obsidian-compatible wiki with HMLR's RAGAS-verified multi-hop reasoning,
temporal conflict resolution, and cross-topic identity persistence built in.

## Architectural decisions

- **Wiki pages ARE dossiers.** Dossier writes markdown files to `wiki/`
  rather than opaque SQL blobs. YAML frontmatter carries HMLR metadata —
  confidence, supersession chain, source turn IDs, last-updated timestamp.
- **Fact store stays SQL, not markdown.** Fast-changing key-value state
  (API keys, counters, policy version numbers) lives in a SQLite fact
  store. Wiki pages reference the fact store rather than duplicating.
- **Governor handles both ingest types.** On document ingest, the Governor
  runs the Scribe, FactScrubber, and a Summariser in parallel. On
  dialogue, it delegates to HMLR's HMLRClient.chat and post-processes
  touched entities.
- **Retrieval is the lattice.** LatticeCrawler (vector) over `wiki/` and
  `raw/`, plus fact-store lookups, plus the active bridge block. The
  Governor filters candidates for true relevance before hydration.
- **Gardener is HMLR gardener plus Karpathy lint.** One nightly process
  that promotes bridge blocks, resolves contradictions by the documented
  policy, regenerates `index.md`, and flags orphans and stale claims.

## Contradiction-resolution policy

Newer source wins by default, using `last_updated` as the tiebreaker.
Pages marked `confidence: high` — typically human-edited — override older
claims even when the new claim is more recent. True ties flag `[[REVIEW]]`
and are not silently overwritten.

## Model dependency

HMLR has only been verified on gpt-4.1-mini. Dossier inherits this
constraint: running on a different model requires re-running Hydra9 Hard
Mode before the memory guarantees transfer.
