# AGENTS.md

This file is the LLM-facing guide for operating on the Dossier wiki. Karpathy's original gist proposed `CLAUDE.md` *or* `AGENTS.md` for this role; Dossier uses `AGENTS.md` because pi.dev (Mario Zechner's terminal coding agent) expects that name and the same file serves both audiences.

**Read [SCHEMA.md](SCHEMA.md) first for the formal conventions. This file is about *how to act*.**

## Your role

You are maintaining a compiled wiki that sits on top of a state engine (HMLR). Your job is not to re-derive answers from raw sources on every query — it's to keep the compiled artifact correct, and to read the compiled artifact when answering.

## The three operations

### Ingest

When a new file appears in `raw/`:

1. Read it fully.
2. Identify every **entity** (named person, org, product, system) and every **concept** (idea, policy, constraint, invariant) mentioned.
3. For each entity/concept: does a page already exist in `wiki/entities/` or `wiki/concepts/`?
   - **Yes, no conflict:** add a new bullet or paragraph, update frontmatter (`last_updated`, append to `sources`, increment `touched_by`).
   - **Yes, conflict:** apply the contradiction-resolution policy in SCHEMA.md. Newer wins unless `confidence: high` on the older claim. Ties flag `[[REVIEW]]` and do not overwrite.
   - **No:** create a new page with full frontmatter.
4. Write a summary page at `wiki/sources/<date>_<slug>.md` capturing the file's main claims, with `sources: [{raw: "<filename>"}]` in frontmatter.
5. Append a one-line entry to `log.md` under today's heading.
6. **Do not** edit `index.md` by hand — the Gardener regenerates it.

Typical ingest touches 10–15 pages. If you touch fewer than 3, you probably missed something. If you touch more than 25, you're probably writing redundantly — consolidate.

### Query

When asked a question:

1. Start at `index.md` to find candidate pages (if the index is still manageable). Past ~200 entries, rely on the vector retrieval that `dossier query` wires up for you.
2. Read the 3–5 most relevant pages fully. Follow wikilinks.
3. Check the fact store for any named keys mentioned in the query (the CLI exposes this).
4. Synthesise an answer **with citations to wiki pages and raw sources**. Format: `[entities/alice]` or `[raw/2026-04-24_article_X.md]`.
5. If the answer is non-trivially new — synthesis that didn't exist before — consider filing it as a new concept or comparison page. Flag it for Gardener review rather than writing directly.

### Lint (Gardener)

When asked to lint or consolidate:

1. Walk every page under `wiki/`. Check frontmatter is well-formed.
2. Find orphans: pages not reachable from `index.md` and not referenced from any other page or source summary. Mark `orphan: true` in frontmatter.
3. Find stale claims: `last_updated > 90 days` AND `confidence: low`. Mark with `[[STALE]]` inline.
4. Find missing cross-references: if page A mentions page B's name but doesn't link to B, auto-insert `[[path/to/b]]`.
5. Walk supersession chains from newest back. If chain breaks (referenced prior page missing), log it.
6. Regenerate `index.md` from current `wiki/` contents.
7. Append a gardener summary to `log.md` — how many pages touched, how many conflicts resolved, how many flagged.

## What not to do

- **Don't put fast-changing state in markdown.** API keys, counters, version numbers → fact store. Pages *reference* the fact store, not *duplicate* it.
- **Don't silently overwrite on conflict.** Always either merge, supersede (with explicit frontmatter), or flag `[[REVIEW]]`. No lost claims.
- **Don't edit `index.md` or `log.md` structure by hand.** The Gardener owns the format. Append to `log.md` under today's heading is fine; rewriting past entries is not.
- **Don't delete raw sources.** They're immutable. If one is wrong, add a correction as a new dated file and let the Gardener supersede.
- **Don't summarise a source without leaving a `wiki/sources/` page.** Future-you needs the breadcrumb.

## Model tested

HMLR is verified on **gpt-4.1-mini only**. Other models may produce invalid frontmatter or drift on the supersession logic. If running on a different model, re-run `tests/bench/` before trusting the wiki.
