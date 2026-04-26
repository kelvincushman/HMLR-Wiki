"""Ingest paths — document and dialogue.

Document ingest (Karpathy): read file → Scribe + FactScrubber + Summariser in
parallel → WikiWriter applies updates → append to log.md.

Dialogue ingest (HMLR): delegate to HMLR's engine, mark touched wiki pages
for Gardener attention on the next pass.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from dossier import frontmatter as fm
from dossier.chunk_engine import chunk_file
from dossier.config import DossierConfig
from dossier.fact_scrubber import FactScrubber
from dossier.governor import Governor, Route
from dossier.hmlr_adapter import HMLREngine, HMLRResponse
from dossier.scribe import Scribe
from dossier.storage import BridgeBlockStore, FactStore
from dossier.wiki_writer import WikiWriter, WriteResult


@dataclass
class IngestResult:
    route: Route
    source: Path | None
    pages_written: list[WriteResult]
    facts_written: int
    log_message: str


def ingest_document(
    source_path: Path,
    cfg: DossierConfig | None = None,
) -> IngestResult:
    """Full document-ingest flow. Synchronous — OK to call from a script or REPL."""
    cfg = cfg or DossierConfig.discover()
    cfg.ensure_dirs()

    governor = Governor()
    decision = governor.classify(source_path=source_path)
    assert decision.route is Route.INGEST_DOCUMENT, "Governor misrouted"

    chunks = chunk_file(source_path)
    if not chunks:
        raise ValueError(f"source {source_path} produced zero chunks — empty file?")

    fact_store = FactStore(cfg.facts_db)
    writer = WikiWriter(cfg)

    scribe = Scribe()
    scribe_result = scribe.process(chunks)

    scrubber = FactScrubber(fact_store, source=str(source_path))
    facts = scrubber.scrub(chunks)

    source_ref = fm.SourceRef(raw=source_path.name)
    written: list[WriteResult] = []

    for entity in scribe_result.entities:
        body = _render_entity_body(entity.evidence)
        written.append(
            writer.upsert_entity(
                entity.name,
                body=body,
                source=source_ref,
                aliases=entity.aliases,
                confidence="medium",
            )
        )

    for concept in scribe_result.concepts:
        body = _render_concept_body(concept.evidence)
        written.append(
            writer.upsert_concept(
                concept.name,
                body=body,
                source=source_ref,
                confidence="medium",
            )
        )

    summary = _render_source_summary(chunks, scribe_result, facts)
    written.append(
        writer.write_source_summary(
            source_path,
            title=source_path.stem.replace("_", " ").title(),
            body=summary,
        )
    )

    log_msg = (
        f"ingested `raw/{source_path.name}` — "
        f"{len(scribe_result.entities)} entities, "
        f"{len(scribe_result.concepts)} concepts, "
        f"{len(facts)} facts"
    )
    writer.append_log(log_msg)

    return IngestResult(
        route=Route.INGEST_DOCUMENT,
        source=source_path,
        pages_written=written,
        facts_written=len(facts),
        log_message=log_msg,
    )


async def ingest_dialogue(
    message: str,
    *,
    engine: HMLREngine,
    session_id: str = "default_session",
    cfg: DossierConfig | None = None,
    bridge_store: BridgeBlockStore | None = None,
) -> HMLRResponse:
    """Dialogue turn path. Delegates to HMLR and touches bridge blocks for Gardener."""
    cfg = cfg or DossierConfig.discover()
    bridge_store = bridge_store or BridgeBlockStore()
    block = bridge_store.active(session_id) or bridge_store.open(session_id, topic=_guess_topic(message))
    block.turns.append({"role": "user", "content": message})
    response = await engine.chat(message, session_id=session_id)
    block.turns.append({"role": "assistant", "content": response.content})
    return response


# --- body rendering --------------------------------------------------------


def _render_entity_body(evidence: list[str]) -> str:
    if not evidence:
        return "_No evidence snippets recorded yet._\n"
    lines = ["## Evidence", ""]
    for e in evidence[:5]:
        lines.append(f"- {e}")
    return "\n".join(lines) + "\n"


def _render_concept_body(evidence: list[str]) -> str:
    if not evidence:
        return "_No evidence snippets recorded yet._\n"
    lines = ["## Evidence", ""]
    for e in evidence[:5]:
        lines.append(f"- {e}")
    return "\n".join(lines) + "\n"


def _render_source_summary(chunks, scribe_result, facts) -> str:
    entity_names = sorted({e.name for e in scribe_result.entities})
    concept_names = sorted({c.name for c in scribe_result.concepts})
    first = chunks[0].text.strip().splitlines()[:3] if chunks else []
    lead = "\n".join(first)
    lines = [
        "## Summary",
        "",
        lead or "_(no lead text extracted)_",
        "",
        f"## Entities ({len(entity_names)})",
        "",
    ]
    lines.extend(f"- [[entities/{_slug(n)}]]" for n in entity_names) if entity_names else lines.append("_none detected_")
    lines += ["", f"## Concepts ({len(concept_names)})", ""]
    lines.extend(f"- [[concepts/{_slug(n)}]]" for n in concept_names) if concept_names else lines.append("_none detected_")
    lines += ["", f"## Facts ({len(facts)}) extracted into fact store", ""]
    for f in facts[:10]:
        lines.append(f"- `{f.subject}` {f.predicate} `{f.value}`")
    if len(facts) > 10:
        lines.append(f"- …and {len(facts) - 10} more")
    lines.append(f"\n_{_dt.date.today().isoformat()} — ingested by dossier_")
    return "\n".join(lines) + "\n"


def _slug(name: str) -> str:
    from slugify import slugify

    return slugify(name, separator="_", max_length=60) or "untitled"


def _guess_topic(message: str) -> str:
    words = message.split()
    return " ".join(words[:6]) or "conversation"
