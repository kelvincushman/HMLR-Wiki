"""Model-backed pipeline for the CLI, switched on with ``DOSSIER_PIPELINE=llm``.

The implementation lives in ``autoresearch/memory.py``: that file is the
autoresearch loop's single file under iteration (see
``autoresearch/program.md``) and the harness imports it from there, so it
stays put. This module loads it — from the source checkout when present
(editable installs, so loop edits take effect), otherwise from the copy the
wheel build ships as ``dossier/_memory.py`` — and adds the CLI glue: turning
retrieved contexts into a grounded answer with its sources.

Without the switch the CLI keeps the heuristic, model-free path.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from dossier.config import DossierConfig

_MODULE_NAME = "dossier._memory"
_CHECKOUT_MEMORY = Path(__file__).resolve().parents[2] / "autoresearch" / "memory.py"


def enabled() -> bool:
    return os.environ.get("DOSSIER_PIPELINE", "").strip().lower() == "llm"


def load_memory() -> ModuleType:
    """Return the autoresearch memory module (cached after the first load)."""
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]
    if _CHECKOUT_MEMORY.is_file():
        spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CHECKOUT_MEMORY)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(_MODULE_NAME)  # wheel install: force-included copy


def check_deps() -> None:
    """Fail early with an install hint instead of an ImportError mid-ingest."""
    missing = [m for m in ("openai", "langchain_openai") if importlib.util.find_spec(m) is None]
    if missing:
        raise RuntimeError(
            f"DOSSIER_PIPELINE=llm needs {', '.join(missing)}; install with: pip install 'dossier[llm]'"
        )


def describe() -> dict[str, str]:
    """Effective model settings, for `dossier doctor`."""
    m = load_memory()
    return {
        "llm_model": m.LLM_MODEL,
        "llm_base_url": os.environ.get("DOSSIER_ANSWER_BASE_URL") or "(OpenAI default)",
        "llm_extra_body": str(m._llm_extra_body() or "(none)"),
        "embed_model": m.EMBED_MODEL,
        "embed_base_url": os.environ.get("OPENAI_BASE_URL") or "(OpenAI default)",
    }


def ingest(source: Path, cfg: DossierConfig) -> dict[str, Any]:
    cfg.ensure_dirs()
    return load_memory().ingest(source, cfg)


def consolidate(cfg: DossierConfig) -> dict[str, Any]:
    cfg.ensure_dirs()
    return load_memory().consolidate(cfg)


@dataclass
class Answer:
    text: str
    contexts: list[dict[str, Any]]


def answer(question: str, cfg: DossierConfig) -> Answer:
    """Retrieve, answer from the contexts only, then drop unsupported sentences."""
    cfg.ensure_dirs()
    m = load_memory()
    contexts = m.retrieve(question, cfg)
    if not contexts:
        return Answer("", [])
    draft = m._text(m._get_llm(temperature=0).invoke(m.build_prompt(question, contexts)))
    return Answer(m.synthesize(draft, contexts, question).strip(), contexts)
