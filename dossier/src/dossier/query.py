"""Query path: crawl lattice → Governor filter → ContextHydrator → (optional LLM)."""

from __future__ import annotations

from dataclasses import dataclass

from dossier.config import DossierConfig
from dossier.context_hydrator import ContextHydrator, HydratedContext
from dossier.governor import Governor
from dossier.lattice_crawler import Candidate, LatticeCrawler
from dossier.storage import BridgeBlockStore, FactStore


@dataclass
class QueryResult:
    question: str
    candidates: list[Candidate]
    hydrated: HydratedContext


def query(
    question: str,
    cfg: DossierConfig | None = None,
    *,
    fact_store: FactStore | None = None,
    bridge_store: BridgeBlockStore | None = None,
    limit: int = 10,
) -> QueryResult:
    """Return the hydrated prompt and the candidates that grounded it.

    This does NOT call an LLM. Callers decide how to finish — feed the prompt
    to HMLR, to an OpenAI SDK call, to a LangGraph node, whatever. Keeping
    the prompt as a return value keeps this pure and testable.
    """
    cfg = cfg or DossierConfig.discover()
    cfg.ensure_dirs()
    fact_store = fact_store or FactStore(cfg.facts_db)
    bridge_store = bridge_store or BridgeBlockStore()

    crawler = LatticeCrawler(cfg, fact_store, bridge_store)
    candidates = crawler.search(question, limit=limit)

    governor = Governor()
    filtered_dicts = governor.filter_candidates(
        question,
        [{"text": c.text, "_cand": c} for c in candidates],
        max_candidates=limit,
    )
    filtered = [d["_cand"] for d in filtered_dicts] or candidates[:limit]

    hydrator = ContextHydrator()
    hydrated = hydrator.hydrate(question, filtered)
    return QueryResult(question=question, candidates=filtered, hydrated=hydrated)
