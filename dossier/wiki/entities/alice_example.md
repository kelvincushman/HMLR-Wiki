---
kind: entity
name: Alice Example
aliases: []
confidence: high
last_updated: 2026-04-24
sources: []
supersedes: []
touched_by:
  - session: seed
    turn: 0
---

# Alice Example

> Seed page. Demonstrates the entity-page frontmatter shape. Delete when real entities appear.

## Identity-persistence fields

Every entity page carries frontmatter that the Gardener uses to detect contradictions across pages:

- `confidence`: `low` | `medium` | `high` — how much the Gardener trusts this page when resolving conflicts
- `sources`: list of `raw/<file>` or `{session, turn}` references that grounded each claim
- `supersedes`: list of prior pages/claims this page replaces (temporal updates)
- `touched_by`: sessions/turns that mentioned this entity but didn't fully rewrite the page — Gardener uses this to decide whether a refresh is due

## Example claim

Alice is a vegetarian. This is a user-invariant: any suggestion that conflicts (e.g. recommending a steakhouse) should be filtered out at retrieval time. See [[concepts/memory_lattice]] for how the lattice enforces this.

## Cross-references

- [[concepts/memory_lattice]]
