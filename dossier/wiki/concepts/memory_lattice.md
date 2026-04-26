---
kind: concept
name: Memory lattice
aliases:
  - lattice
  - three-layer memory
confidence: high
last_updated: 2026-04-24
sources: []
supersedes: []
---

# Memory lattice

The unified memory layer Dossier exposes to the LLM. Three stores, one query path.

## The three stores

1. **Wiki pages** — markdown under `wiki/`. Compiled, slow-changing, human-readable. Each page is a dossier for one entity/concept/source. Frontmatter carries confidence + supersession + sources.
2. **Fact store** — SQL key-value table under `.hmlr/facts.db`. Fast-changing state (API key versions, policy revisions, counters). Overwrites on temporal update; wiki pages link *to* the fact store for current state.
3. **Bridge blocks** — short-term cache of the active topic. Cleared/promoted by the Gardener on each pass.

## The query path

Retrieval runs all three in parallel, then the Governor filters candidates for true relevance before ContextHydrator assembles the prompt:

```
query → [LatticeCrawler (vector over wiki/ + raw/),
         fact store (exact lookups),
         bridge blocks (active topic)]
      → Governor filter (Key 2: true relevance)
      → ContextHydrator
      → LLM
```

## Why markdown and not just SQL

- Git-diffable: every wiki change shows up in review
- Obsidian-compatible: humans can browse and edit
- The compiled form *is* the human-readable form — no second surface to keep in sync

## Why not just markdown

- Exact lookups on fast-changing keys are slow in markdown, fast in SQL
- Vector index over wiki is fine; vector index over the whole corpus every turn is not

## Cross-references

- [[entities/alice_example]]
