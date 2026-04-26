"""The Governor — routing brain for ingest/query classification.

HMLR's Governor decides, for each incoming signal, whether the system is
resuming an active topic (extend the bridge block) or starting a new one.
Dossier's Governor extends this with a third branch: document ingest, where
the source is a file rather than a dialogue turn.

This module is deliberately synchronous and lightweight. The heavy lifting
(embeddings, retrieval, LLM calls) happens in the path modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Route(str, Enum):
    INGEST_DOCUMENT = "ingest_document"
    INGEST_DIALOGUE = "ingest_dialogue"
    QUERY = "query"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str
    session_id: str | None = None
    source_path: Path | None = None


class Governor:
    """Classifies every call at the top of the pipeline.

    The classification rules are intentionally simple and rule-based. HMLR's
    real Governor also runs a *Key 2* relevance filter over retrieved
    candidates; that filter lives in ``lattice_crawler.Governor.filter`` so
    both paths can share it without pulling the full engine.
    """

    def classify(
        self,
        *,
        source_path: Path | None = None,
        message: str | None = None,
        session_id: str | None = None,
    ) -> RouteDecision:
        if source_path is not None:
            path = Path(source_path)
            if not path.exists():
                raise FileNotFoundError(f"source not found: {path}")
            return RouteDecision(
                route=Route.INGEST_DOCUMENT,
                reason=f"source_path given: {path.name}",
                source_path=path,
            )
        if message is None:
            raise ValueError("Governor.classify() needs either source_path or message")
        if _looks_like_query(message):
            return RouteDecision(
                route=Route.QUERY,
                reason="message pattern matched query heuristic",
                session_id=session_id,
            )
        return RouteDecision(
            route=Route.INGEST_DIALOGUE,
            reason="default — treat as dialogue turn",
            session_id=session_id,
        )

    def filter_candidates(
        self,
        query: str,
        candidates: list[dict],
        *,
        max_candidates: int = 5,
    ) -> list[dict]:
        """Key 2 relevance filter: keep only candidates that are truly relevant.

        The real HMLR uses an LLM call here. The Dossier MVP uses a cheap
        token-overlap heuristic; swap in an LLM scorer at integration time.
        """
        query_tokens = set(_normalise(query).split())
        scored = []
        for cand in candidates:
            cand_text = _normalise(cand.get("text", "") or cand.get("excerpt", ""))
            cand_tokens = set(cand_text.split())
            if not cand_tokens:
                continue
            overlap = len(query_tokens & cand_tokens)
            if overlap == 0:
                continue
            scored.append((overlap, cand))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _, c in scored[:max_candidates]]


_QUERY_HEAD_TOKENS = {
    "what", "who", "when", "where", "why", "how",
    "did", "does", "do", "is", "are", "was", "were",
    "can", "could", "should", "would", "will",
    "tell", "explain", "summarise", "summarize", "list", "show",
}


def _looks_like_query(message: str) -> bool:
    stripped = message.strip()
    if stripped.endswith("?"):
        return True
    first = stripped.split(maxsplit=1)[0].lower() if stripped else ""
    return first in _QUERY_HEAD_TOKENS


def _normalise(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
