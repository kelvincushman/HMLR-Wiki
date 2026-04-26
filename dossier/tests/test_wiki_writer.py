from dossier import frontmatter as fm
from dossier.config import DossierConfig
from dossier.wiki_writer import WikiWriter


def test_upsert_entity_creates_new_page(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    result = w.upsert_entity(
        "Alice",
        body="Alice is a vegetarian.\n",
        source=fm.SourceRef(raw="2026-04-24_article.md"),
        confidence="medium",
    )
    assert result.created
    assert result.path.exists()
    page = fm.loads(result.path.read_text(encoding="utf-8"))
    assert page.kind == "entity"
    assert page.name == "Alice"
    assert "vegetarian" in page.body


def test_upsert_entity_appends_non_conflicting_content(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    w.upsert_entity("Alice", body="Fact A.\n", source=fm.SourceRef(raw="a.md"))
    result = w.upsert_entity("Alice", body="Fact B.\n", source=fm.SourceRef(raw="b.md"))
    assert not result.created
    text = result.path.read_text(encoding="utf-8")
    assert "Fact A." in text and "Fact B." in text


def test_high_confidence_page_not_overwritten_by_lower(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    w.upsert_entity(
        "Alice",
        body="Alice is a vegetarian.\n",
        source=fm.SourceRef(raw="a.md"),
        confidence="high",
    )
    w.upsert_entity(
        "Alice",
        body="Alice is not a vegetarian.\n",
        source=fm.SourceRef(raw="b.md"),
        confidence="low",
    )
    page = fm.loads(w.entity_path("Alice").read_text(encoding="utf-8"))
    assert "Alice is a vegetarian." in page.body
    # the attempted contradicting line from a lower-confidence source should be dropped
    assert "is not a vegetarian" not in page.body


def test_equal_confidence_contradiction_flags_review(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    w.upsert_entity(
        "Alice",
        body="Alice is a vegetarian.\n",
        source=fm.SourceRef(raw="a.md"),
        confidence="medium",
    )
    result = w.upsert_entity(
        "Alice",
        body="Alice is not a vegetarian.\n",
        source=fm.SourceRef(raw="b.md"),
        confidence="medium",
    )
    assert result.review_flagged
    text = result.path.read_text(encoding="utf-8")
    assert "[[REVIEW]]" in text


def test_append_log_inserts_under_today_heading(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    w.append_log("ingested something")
    log_text = (dossier_project.wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "ingested something" in log_text


def test_write_source_summary_uses_dated_filename(dossier_project: DossierConfig):
    w = WikiWriter(dossier_project)
    import datetime as _dt

    raw = dossier_project.raw_dir / "2026-04-24_article.md"
    raw.write_text("hello")
    result = w.write_source_summary(raw, title="Article", body="Summary body.\n", ingested_on=_dt.date(2026, 4, 24))
    assert result.path.name.startswith("2026-04-24_")
    assert result.path.name.endswith(".md")
