# The LLM Wiki pattern

Andrej Karpathy describes a personal knowledge system where an LLM
incrementally builds and maintains a persistent wiki rather than
re-deriving answers from raw documents on every query. The key insight is
that knowledge should compound across sessions.

## Three-layer architecture

1. **Raw sources** — immutable collection of curated documents (articles,
   papers, images, data files) that serve as the source of truth.
2. **The wiki** — directory of LLM-generated markdown files containing
   summaries, entity pages, concept pages, comparisons, and synthesis. The
   LLM owns this layer entirely, creating, updating, and maintaining
   cross-references.
3. **The schema** — configuration document (CLAUDE.md or AGENTS.md)
   specifying wiki structure, conventions, and workflows for ingestion,
   querying, and maintenance.

## Key operations

- **Ingest** — process new sources by reading them, extracting key
  information, updating relevant wiki pages, maintaining cross-references,
  and logging the activity.
- **Query** — search wiki pages for relevant information, synthesize
  answers with citations, and file valuable results back into the wiki as
  new pages.
- **Lint** — periodically health-check the wiki for contradictions,
  staleness, orphaned pages, and missing cross-references.

## Supporting files

- `index.md` — a content-oriented catalog listing all wiki pages with summaries.
- `log.md` — an append-only chronological record of ingests, queries, and
  maintenance activities.

## Core distinction from RAG

Unlike traditional RAG systems that retrieve from raw documents at query
time, this pattern compiles knowledge once during ingestion, allowing
subsequent queries to benefit from accumulated synthesis and cross-linking
rather than repeating discovery work.
