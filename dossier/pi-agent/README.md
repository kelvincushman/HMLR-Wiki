# `dossier` — pi.dev skill

A [pi.dev](https://pi.dev/) package that teaches Mario Zechner's terminal coding agent how to operate the Dossier memory lattice.

## What it gives you

- **Skill:** `dossier` — wraps the `dossier` CLI (`ingest`, `query`, `gardener`, `chat`, `doctor`) as pi tools so the agent can call them without shell detours.
- **System prompt:** [SYSTEM.md](SYSTEM.md) — the one-line role definition pi loads on startup.
- **Context doc:** [AGENTS.md](AGENTS.md) — symlink / mirror of the project-level `AGENTS.md`. pi reads this the same way Karpathy's pattern expects.

## Install

Install as an npm / git-installable pi package:

```bash
pi plugin install dossier         # when published
# or from this checkout:
pi plugin install ./dossier/pi-agent
```

Prerequisites: the `dossier` Python CLI must be on PATH (`pip install -e ../dossier[hmlr]` from the repo root).

## Conventions

pi expects packages to declare themselves in [package.json](package.json). The file here follows the shape from pi.dev's public docs as of 2026-04: `name`, `version`, `pi` block with `skills` / `system` / `agentsDoc` keys. If the schema has shifted, see pi's upstream docs and file an issue on [HMLR-WIKI](https://github.com/kelvincushman/HMLR-WIKI) — the wrapper is intentionally thin so updates are easy.
