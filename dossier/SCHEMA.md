# SCHEMA.md

Conventions the LLM follows when ingesting, querying, or linting the Dossier wiki. This is Karpathy's "schema document" role — the file both the LLM and the Gardener read before touching `wiki/`.

## Directory rules

- `raw/` is immutable. Never edit a file once it's in there. If a source is revised, add a new timestamped file alongside it (`2026-04-24_article_v2.md`) — the Gardener will mark the old one as superseded.
- `wiki/` is LLM-owned. Humans can edit, but the Gardener treats human edits as first-class: frontmatter `edited_by: human` flips `confidence` to `high` unless explicitly lowered.
- `.hmlr/` is engine-owned. Do not edit by hand. Do not commit contents (see `.gitignore`) — schema is stable but blob contents are not human-readable.
- `index.md` and `log.md` are Gardener-regenerated. Edits are lost on next pass.

## Page kinds

Every wiki page has a `kind` field in frontmatter. Valid values:

| kind | directory | purpose |
|------|-----------|---------|
| `entity` | `entities/` | one page per person, org, product, location, system |
| `concept` | `concepts/` | one page per idea, policy, constraint, invariant |
| `source` | `sources/` | one summary page per file in `raw/` |
| `index` | `index.md` | Gardener-generated catalog |
| `log` | `log.md` | append-only activity log |

New kinds require: (1) a new subdirectory, (2) a frontmatter entry in `frontmatter.py`, (3) a writer that knows how to populate it, (4) a lint rule in `gardener.py`, (5) an `index.md` section.

## Required frontmatter

Every page (except `index` and `log`):

```yaml
---
kind: entity              # one of the kinds above
name: "Alice"             # display name; filename is the slug
aliases: ["Ali"]          # other names the Scribe should dedupe against
confidence: high          # low | medium | high — Gardener uses this for conflict resolution
last_updated: 2026-04-24  # ISO date; Gardener updates on write
sources:                  # what grounded each claim
  - raw: "2026-04-24_article_X.md"
  - session: "abc123"
    turn: 42
supersedes: []            # prior pages/claims this one replaces
touched_by: []            # sessions/turns that mentioned this but didn't rewrite it
edited_by: llm            # llm | human — set by writer, respected by Gardener
---
```

## Naming

- Filenames: slugified (lowercase, dashes or underscores, no spaces). `python-slugify` handles this; see `wiki_writer.slugify()`.
- Source filenames: `YYYY-MM-DD_<slug>.md`. The date prefix anchors temporal ordering and lets the Gardener walk chronologically.
- Wikilinks: `[[entities/alice]]` or `[[concepts/memory_lattice]]`. Use the path, not just the filename — disambiguates across kinds.

## Contradiction-resolution policy

When the Gardener finds two pages (or a page and a fact-store row) making conflicting claims:

1. **Newer source wins** by default. `last_updated` is the tiebreaker.
2. **`confidence: high` overrides older claims** — e.g. a human-edited page is not overwritten by a low-confidence LLM summary.
3. **Ties flag for human review.** The Gardener writes `[[REVIEW]]` to the page and logs it to `log.md`. No silent overwrites.
4. **Fact-store beats wiki for fast-changing keys.** If `facts.db` says `api_key_version = 7` and a wiki page says `api_key_version = 5`, the page gets marked stale, not the fact store.

## Ingest workflow — document

When a file lands in `raw/`:

1. `ChunkEngine` chunks + embeds the file. Chunks stored in `.hmlr/embeddings/`.
2. `Governor` classifies: ingest_document.
3. In parallel:
   - `Scribe` reads the file and identifies entities and concepts mentioned. Queues wiki page updates.
   - `FactScrubber` extracts explicit key-value claims (e.g. `Alice.is_vegetarian = true`) into the fact store.
   - `Summariser` writes `wiki/sources/<date>_<slug>.md` summarising the file.
4. `WikiWriter` applies queued updates. If a page already exists and the new claim conflicts, it consults the policy above and either merges or flags.
5. Append one entry to `log.md`.

## Ingest workflow — dialogue

Vanilla HMLR handles the turn. Any entities or concepts touched during the conversation are recorded in the `touched_by` frontmatter of the corresponding wiki pages (or new pages are queued) so the Gardener can decide whether a rewrite is needed.

## Query workflow

```
user query
  ↓ Governor.classify(): query
  ↓ parallel:
    • LatticeCrawler: vector search over wiki/ + raw/ chunks
    • fact_store.lookup(): exact lookups for any named keys
    • bridge_blocks.active(): current topic context
  ↓ Governor.filter(): Key 2 relevance filter
  ↓ ContextHydrator: assemble prompt with citations
  ↓ LLM answers
  ↓ if answer is high-value (heuristic or explicit), file it as a new wiki page
```

## Gardener / lint workflow

Runs on demand (`dossier gardener`) or on cron.

1. **Promote.** Bridge blocks that have stabilised → wiki pages (concepts, entities).
2. **Resolve.** Walk frontmatter supersession chains, apply the contradiction-resolution policy, update pages.
3. **Lint.**
   - Orphan detection: wiki pages not reachable from any other page *and* not referenced by any source get `orphan: true`.
   - Stale claims: pages with `last_updated` older than a threshold *and* `confidence: low` get flagged.
   - Missing cross-references: entity pages that mention another entity by name but don't link to its page get auto-linked.
4. **Rebuild `index.md`** from current `wiki/` contents.
5. **Append gardener summary to `log.md`.**

## What not to put in wiki pages

- **Fast-changing state.** API key versions, counters, session tokens, per-user overrides. These belong in the fact store (`.hmlr/facts.db`). Reference the fact store from the page; don't duplicate.
- **Raw verbatim source text.** Summarise. The raw text is already in `raw/`.
- **Conversation transcripts.** Bridge blocks hold these; the Gardener decides what rises to a wiki page.

## Obsidian compatibility

Pages open cleanly in Obsidian. Use `[[wikilinks]]`, YAML frontmatter, and standard markdown. The `.hmlr/` folder is gitignored and Obsidian ignores dotfiles by default.
