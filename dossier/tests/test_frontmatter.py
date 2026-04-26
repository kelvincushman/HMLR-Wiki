import datetime as _dt

import pytest

from dossier import frontmatter as fm


def test_roundtrip_preserves_core_fields():
    page = fm.Page(
        kind="entity",
        name="Alice",
        body="She is a vegetarian.\n",
        aliases=["Ali"],
        confidence="high",
        last_updated=_dt.date(2026, 4, 24),
        sources=[fm.SourceRef(raw="2026-04-24_article.md")],
    )
    text = fm.dumps(page)
    reparsed = fm.loads(text)
    assert reparsed.kind == "entity"
    assert reparsed.name == "Alice"
    assert reparsed.aliases == ["Ali"]
    assert reparsed.confidence == "high"
    assert reparsed.last_updated == _dt.date(2026, 4, 24)
    assert reparsed.sources[0].raw == "2026-04-24_article.md"
    assert "vegetarian" in reparsed.body


def test_rejects_missing_frontmatter():
    with pytest.raises(fm.FrontmatterError):
        fm.loads("# no frontmatter here\n")


def test_rejects_unterminated_frontmatter():
    with pytest.raises(fm.FrontmatterError):
        fm.loads("---\nkind: entity\nname: x\n\n(body without close)\n")


def test_rejects_invalid_kind():
    with pytest.raises(fm.FrontmatterError):
        fm.Page(kind="not-a-kind", name="x")


def test_rejects_invalid_confidence():
    with pytest.raises(fm.FrontmatterError):
        fm.Page(kind="entity", name="x", confidence="absolute")


def test_preserves_extra_fields_on_roundtrip():
    text = (
        "---\n"
        "kind: entity\n"
        "name: Alice\n"
        "confidence: medium\n"
        "last_updated: 2026-04-24\n"
        "custom_field: hello\n"
        "---\n\nbody\n"
    )
    page = fm.loads(text)
    assert page.extra.get("custom_field") == "hello"
    redumped = fm.dumps(page)
    assert "custom_field: hello" in redumped


def test_source_ref_session_turn():
    page = fm.Page(
        kind="concept",
        name="x",
        sources=[fm.SourceRef(session="abc", turn=7)],
    )
    text = fm.dumps(page)
    reparsed = fm.loads(text)
    assert reparsed.sources[0].session == "abc"
    assert reparsed.sources[0].turn == 7
