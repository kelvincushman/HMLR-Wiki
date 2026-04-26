"""LangGraph integration — layers Dossier's wiki surface over HMLR's LangGraph nodes.

HMLR ships ``hmlr.integrations.langgraph`` with ``hmlr_memory_node`` and
``hmlr_chat_node``. Dossier re-exports them unchanged for dialogue, and adds
``dossier_ingest_node`` for document-ingest turns inside a graph.

This module lazy-imports LangGraph and HMLR so nothing breaks if either
extra is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dossier.config import DossierConfig
from dossier.ingest import ingest_document


def dossier_ingest_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node that ingests a document referenced in state.

    Expected state shape:
        {"source_path": "raw/some_article.md", "project_root": "..."}
    Returns:
        {"ingest_result": {...}}
    """
    src = state.get("source_path")
    if not src:
        raise ValueError("dossier_ingest_node requires state['source_path']")
    project_root = state.get("project_root")
    cfg = DossierConfig.for_root(Path(project_root)) if project_root else DossierConfig.discover()
    result = ingest_document(Path(src), cfg=cfg)
    return {
        "ingest_result": {
            "pages_written": [str(w.path) for w in result.pages_written],
            "facts_written": result.facts_written,
            "log_message": result.log_message,
        }
    }


def hmlr_memory_node(state: dict[str, Any]) -> dict[str, Any]:
    """Re-export of HMLR's ``hmlr_memory_node``. Raises if HMLR is not installed."""
    from hmlr.integrations.langgraph.nodes import hmlr_memory_node as _node  # type: ignore[import-not-found]

    return _node(state)


def hmlr_chat_node(state: dict[str, Any]) -> dict[str, Any]:
    from hmlr.integrations.langgraph.nodes import hmlr_chat_node as _node  # type: ignore[import-not-found]

    return _node(state)
