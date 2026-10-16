"""DOSSIER_PIPELINE=llm — the CLI on the autoresearch memory pipeline.

No network: the chat model is a scripted fake (``_get_llm`` patched on the
loaded module) and ``openai`` is replaced in ``sys.modules`` by a fake whose
embeddings are bag-of-words vectors, so cosine retrieval still behaves.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from click.testing import CliRunner

from dossier import pipeline
from dossier.cli import main
from dossier.storage import FactStore

THINK = "<think>\nThe user wants JSON {not this}. Indices 9,9,9.\n</think>\n\n"


def _embed(text: str, dim: int = 64) -> list[float]:
    vec = [0.0] * dim
    for word in text.lower().split():
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    return vec


class FakeEmbeddings:
    def __init__(self, calls: list[dict]):
        self.calls = calls

    def create(self, *, model: str, input: list[str]):
        self.calls.append({"model": model, "n": len(input)})
        return SimpleNamespace(data=[SimpleNamespace(embedding=_embed(t)) for t in input])


class FakeChat:
    """Answers each pipeline prompt by recognising its fixed instructions.
    Every reply carries a <think> block, as Qwen3-style models emit."""

    def __init__(self, prompts: list[str]):
        self.prompts = prompts

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        if prompt.startswith("Extract entities"):
            body = {
                "entities": [
                    {"name": "Project Falcon", "aliases": ["Falcon"],
                     "summary": "Internal service; chose Postgres over Mongo.",
                     "evidence": ["Falcon will use Postgres."]}
                ],
                "concepts": [{"name": "Database decision", "summary": "Postgres chosen.", "evidence": []}],
            }
            return SimpleNamespace(content=THINK + "```json\n" + json.dumps(body) + "\n```")
        if prompt.startswith("Extract atomic"):
            body = {"facts": [{"subject": "Project Falcon", "predicate": "uses database",
                               "value": "Postgres", "evidence": "Falcon will use Postgres.", "date": None}]}
            return SimpleNamespace(content=THINK + json.dumps(body))
        if prompt.startswith("Break the following"):
            return SimpleNamespace(content=THINK + '["Falcon database", "decision date"]')
        if prompt.startswith("Rank these"):
            return SimpleNamespace(content=THINK + "0,1,2")
        if prompt.startswith("Rewrite the wiki page"):
            return SimpleNamespace(content=THINK + "## Summary\n\nConsolidated Falcon dossier.")
        if prompt.startswith("You are answering"):
            return SimpleNamespace(content=THINK + "Project Falcon uses Postgres. Mars is red.")
        if prompt.startswith("You are a faithfulness filter"):
            return SimpleNamespace(content=THINK + "Project Falcon uses Postgres.")
        raise AssertionError(f"unexpected prompt: {prompt[:80]!r}")


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Turn the llm pipeline on with fake model clients; yields call logs."""
    monkeypatch.setenv("DOSSIER_PIPELINE", "llm")
    prompts: list[str] = []
    embed_calls: list[dict] = []
    fake_openai = ModuleType("openai")
    fake_openai.OpenAI = lambda *a, **k: SimpleNamespace(embeddings=FakeEmbeddings(embed_calls))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setattr(pipeline, "check_deps", lambda: None)
    memory = pipeline.load_memory()
    monkeypatch.setattr(memory, "_get_llm", lambda **_: FakeChat(prompts))
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki").mkdir()
    return SimpleNamespace(root=tmp_path, prompts=prompts, embed_calls=embed_calls, memory=memory)


def _write_source(root: Path, name: str) -> Path:
    path = root / "raw" / name
    path.write_text(
        "# Falcon database decision\n\nProject Falcon will use Postgres, not Mongo. "
        "Decided by the platform team after the load test.\n",
        encoding="utf-8",
    )
    return path


def _cli(root: Path, *args: str):
    result = CliRunner().invoke(main, ["--project", str(root), *args], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


# --- think-block handling --------------------------------------------------


def test_parse_json_block_ignores_leading_think(llm_env):
    m = llm_env.memory
    assert m._parse_json_block(THINK + '{"a": 1}') == {"a": 1}
    assert m._parse_json_block(THINK + '```json\n{"a": 2}\n```') == {"a": 2}
    # server put <think> in the prompt, so only the closing tag comes back
    assert m._parse_json_block('reasoning {x}\n</think>\n{"a": 3}') == {"a": 3}
    assert m._parse_json_block('{"a": 4}') == {"a": 4}


def test_text_strips_think(llm_env):
    m = llm_env.memory
    assert m._text(SimpleNamespace(content=THINK + "answer")) == "answer"
    assert m._text(SimpleNamespace(content="<think>\n\n</think>\n\nanswer")) == "answer"
    assert m._text("plain") == "plain"


# --- model knobs -----------------------------------------------------------


def test_get_llm_extra_body(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    fake_lc = ModuleType("langchain_openai")
    fake_lc.ChatOpenAI = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_lc)
    m = pipeline.load_memory()

    monkeypatch.delenv("DOSSIER_LLM_EXTRA_BODY", raising=False)
    monkeypatch.delenv("DOSSIER_DISABLE_THINKING", raising=False)
    m._get_llm()
    assert "extra_body" not in captured

    monkeypatch.setenv("DOSSIER_LLM_EXTRA_BODY", '{"top_k": 20}')
    monkeypatch.setenv("DOSSIER_DISABLE_THINKING", "1")
    monkeypatch.setenv("DOSSIER_ANSWER_BASE_URL", "http://127.0.0.1:8097/v1")
    m._get_llm()
    assert captured["extra_body"] == {"top_k": 20, "chat_template_kwargs": {"enable_thinking": False}}
    assert captured["base_url"] == "http://127.0.0.1:8097/v1"


def test_embed_model_env(monkeypatch: pytest.MonkeyPatch):
    def fresh():  # EMBED_MODEL is read at import; load a new copy of the module
        monkeypatch.delitem(sys.modules, "dossier._memory", raising=False)
        return pipeline.load_memory()

    monkeypatch.delenv("DOSSIER_EMBED_MODEL", raising=False)
    assert fresh().EMBED_MODEL == "text-embedding-3-small"
    monkeypatch.setenv("DOSSIER_EMBED_MODEL", "qwen3-embedding-8b")
    assert fresh().EMBED_MODEL == "qwen3-embedding-8b"


# --- CLI end to end (fake models) -----------------------------------------


def test_cli_ingest_llm_writes_wiki_and_facts(llm_env):
    src = _write_source(llm_env.root, "falcon.md")
    out = _cli(llm_env.root, "ingest", str(src))
    assert "pipeline: llm" in out
    assert "1 entities, 1 concepts, 1 facts" in out
    assert (llm_env.root / "wiki" / "entities" / "project_falcon.md").exists()
    facts = {f.key: f.value for f in FactStore(llm_env.root / ".hmlr" / "facts.db").all()}
    assert facts == {"project_falcon.uses_database": "Postgres"}


def test_cli_query_llm_prints_grounded_answer_and_sources(llm_env):
    _cli(llm_env.root, "ingest", str(_write_source(llm_env.root, "falcon.md")))
    llm_env.embed_calls.clear()
    out = _cli(llm_env.root, "query", "which database does Falcon use")
    answer, _, sources = out.partition("\nSources:\n")
    assert answer.strip() == "Project Falcon uses Postgres."
    assert "<think>" not in out
    assert "[wiki:entities/project_falcon.md]" in sources
    assert "[fact:project_falcon.uses_database]" in sources
    assert {c["model"] for c in llm_env.embed_calls} == {llm_env.memory.EMBED_MODEL}


def test_cli_query_llm_empty_wiki_skips_model(llm_env):
    out = _cli(llm_env.root, "query", "anything at all")
    assert "No answer grounded in memory" in out
    assert llm_env.prompts == []


def test_cli_gardener_llm_consolidates_then_lints(llm_env):
    for name in ("a.md", "b.md", "c.md"):  # consolidate needs >= 3 sources per page
        _cli(llm_env.root, "ingest", str(_write_source(llm_env.root, name)))
    out = _cli(llm_env.root, "gardener")
    assert "consolidate: 2 pages rewritten" in out
    assert "gardener complete" in out
    page = (llm_env.root / "wiki" / "entities" / "project_falcon.md").read_text(encoding="utf-8")
    assert "Consolidated Falcon dossier." in page
    assert "<think>" not in page


def test_cli_doctor_reports_pipeline(llm_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DOSSIER_DISABLE_THINKING", "1")
    out = _cli(llm_env.root, "doctor")
    assert "pipeline:   llm" in out
    assert "enable_thinking" in out


def test_cli_defaults_to_heuristic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("DOSSIER_PIPELINE", raising=False)
    monkeypatch.setattr(pipeline, "load_memory", lambda: pytest.fail("llm pipeline loaded"))
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki").mkdir()
    src = _write_source(tmp_path, "falcon.md")
    assert "routed: ingest_document" in _cli(tmp_path, "ingest", str(src))
    assert "candidates (" in _cli(tmp_path, "query", "Falcon database")
    assert "pipeline:   heuristic" in _cli(tmp_path, "doctor")
