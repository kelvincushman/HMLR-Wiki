from pathlib import Path

import pytest

from dossier.governor import Governor, Route


def test_routes_document_when_source_path_given(tmp_path: Path):
    src = tmp_path / "x.md"
    src.write_text("hello")
    decision = Governor().classify(source_path=src)
    assert decision.route is Route.INGEST_DOCUMENT
    assert decision.source_path == src


def test_raises_when_source_missing():
    with pytest.raises(FileNotFoundError):
        Governor().classify(source_path=Path("nope.md"))


def test_routes_query_on_question_mark():
    decision = Governor().classify(message="Is Alice a vegetarian?")
    assert decision.route is Route.QUERY


def test_routes_query_on_question_head_token():
    decision = Governor().classify(message="what did Alice say")
    assert decision.route is Route.QUERY


def test_routes_dialogue_for_statements():
    decision = Governor().classify(message="Alice is a vegetarian.")
    assert decision.route is Route.INGEST_DIALOGUE


def test_classify_needs_source_or_message():
    with pytest.raises(ValueError):
        Governor().classify()


def test_filter_candidates_keeps_overlapping():
    gov = Governor()
    cands = [
        {"text": "Alice is a vegetarian and prefers Mediterranean food."},
        {"text": "Bob uses Python for data science."},
        {"text": "Unrelated musing about the weather."},
    ]
    filtered = gov.filter_candidates("what does Alice eat", cands, max_candidates=3)
    assert any("Alice" in c["text"] for c in filtered)
    # the unrelated musing should fall out
    assert not any("weather" in c["text"] for c in filtered)
