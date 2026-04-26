from pathlib import Path

from dossier import frontmatter as fm
from dossier.config import DossierConfig
from dossier.query import query


def _seed_entity(cfg: DossierConfig, name: str, body: str) -> None:
    page = fm.Page(kind="entity", name=name, body=body)
    path = cfg.entities_dir / f"{name.lower()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm.dumps(page), encoding="utf-8")


def test_query_returns_relevant_wiki_candidates(dossier_project: DossierConfig):
    _seed_entity(dossier_project, "alice", "Alice is a vegetarian who prefers Mediterranean food.\n")
    _seed_entity(dossier_project, "bob", "Bob writes Python.\n")
    result = query("what does Alice eat", cfg=dossier_project)
    refs = [c.ref for c in result.candidates]
    assert any("alice" in r for r in refs), refs
    # prompt should mention the citation
    assert "entities/alice" in result.hydrated.prompt


def test_query_pulls_from_fact_store(dossier_project: DossierConfig):
    from dossier.storage import FactStore

    fs = FactStore(dossier_project.facts_db)
    fs.put("alice.is", "vegetarian", source="seed")
    result = query("tell me about alice is", cfg=dossier_project, fact_store=fs)
    assert any(c.kind == "fact" for c in result.candidates)


def test_query_produces_hydrated_prompt(dossier_project: DossierConfig):
    _seed_entity(dossier_project, "alice", "vegetarian\n")
    result = query("alice diet", cfg=dossier_project)
    assert "Question" in result.hydrated.prompt
    assert "alice diet" in result.hydrated.prompt
