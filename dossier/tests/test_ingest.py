from pathlib import Path

import pytest

from dossier.config import DossierConfig
from dossier.governor import Route
from dossier.hmlr_adapter import build_engine
from dossier.ingest import ingest_dialogue, ingest_document


def test_document_ingest_writes_pages_facts_log(
    dossier_project: DossierConfig, sample_raw_file: Path
):
    result = ingest_document(sample_raw_file, cfg=dossier_project)

    assert result.route is Route.INGEST_DOCUMENT
    assert result.source == sample_raw_file
    assert result.facts_written > 0, "FactScrubber should extract at least 'Alice is vegetarian' etc"
    assert len(result.pages_written) > 0

    # source summary was written under wiki/sources/
    source_pages = list(dossier_project.sources_dir.glob("*.md"))
    assert len(source_pages) == 1

    # Alice should have an entity page
    alice_page = dossier_project.entities_dir / "alice.md"
    assert alice_page.exists(), f"expected entity page at {alice_page}"

    # log.md got the entry
    log_text = (dossier_project.wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "ingested" in log_text
    assert sample_raw_file.name in log_text


def test_document_ingest_populates_fact_store(
    dossier_project: DossierConfig, sample_raw_file: Path
):
    from dossier.storage import FactStore

    ingest_document(sample_raw_file, cfg=dossier_project)
    fs = FactStore(dossier_project.facts_db)
    all_facts = fs.all()
    assert len(all_facts) > 0
    # at least one fact should be about Alice
    assert any("alice" in f.key.lower() for f in all_facts)


def test_empty_source_raises(dossier_project: DossierConfig, tmp_path: Path):
    empty = dossier_project.raw_dir / "empty.md"
    empty.write_text("")
    with pytest.raises(ValueError):
        ingest_document(empty, cfg=dossier_project)


@pytest.mark.asyncio
async def test_dialogue_ingest_uses_stub_when_hmlr_missing(dossier_project: DossierConfig):
    engine = build_engine(db_path=str(dossier_project.facts_db), force_stub=True)
    try:
        response = await ingest_dialogue(
            "My name is Kelvin",
            engine=engine,
            session_id="t1",
            cfg=dossier_project,
        )
        assert response.metadata.get("stub") is True
        assert "heard you say" in response.content
    finally:
        engine.close()
