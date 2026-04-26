# pi.dev AGENTS.md — Dossier operating guide

This file is the project-level operating guide for pi.dev when working in a
Dossier project. It mirrors the top-level [../AGENTS.md](../AGENTS.md) —
updates should be made there and synced here (or just `cp` it).

## Role

You are maintaining a compiled wiki that sits on top of a state engine
(HMLR). Your job is not to re-derive answers from raw sources on every
query — it's to keep the compiled artifact correct, and to read the compiled
artifact when answering.

## Three operations, four tools

The `dossier` skill exposes four tools. Pick by intent:

| Intent | Tool | Notes |
|--------|------|-------|
| User dropped a new file in `raw/` | `dossier.ingest` | pass the file path |
| User asked a question | `dossier.query` | returns candidates + hydrated prompt |
| Things feel drift-y; nightly pass | `dossier.gardener` | idempotent; run after batch ingests |
| "Is anything broken?" | `dossier.doctor` | reads-only; checks layout + deps |

For dialogue (no ingest, no query), just chat — HMLR's own memory path
handles it transparently if you use the `dossier` Python CLI's `chat`
command. pi.dev does not expose chat directly; `dossier.query` is the
read path and `dossier.ingest` is the write path.

## Conventions

See [../SCHEMA.md](../SCHEMA.md) for the formal rules. The load-bearing ones:

- **Never hand-edit `index.md` or `log.md`.** Gardener owns them.
- **Never delete files in `raw/`.** Superseded sources get a new dated file.
- **Fast-changing state (keys, counters, versions) → fact store, not wiki pages.**
- **On conflict: newer wins unless older is `confidence: high`. Ties flag `[[REVIEW]]`.**
- **Cite every non-trivial claim when answering** — `[entities/alice]`, `[raw/2026-04-24_article.md]`, `fact:alice.is`.

## What pi should not do

- Do not run `rm`, `mv`, or any destructive filesystem op inside `wiki/` or
  `raw/`. If a page is wrong, fix it via a fresh ingest or a Gardener pass.
- Do not bypass the skill to call Python directly unless the user asks —
  the tools encode the conventions and the wrapper keeps output consistent.
- Do not promise "I've updated the wiki" without actually calling
  `dossier.ingest` or `dossier.gardener`. The compiled artifact only
  changes through those tools.
