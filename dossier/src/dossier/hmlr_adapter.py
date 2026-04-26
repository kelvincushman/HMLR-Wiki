"""Adapter around HMLR's public client.

If the ``hmlr`` package is installed, this module wraps ``hmlr.HMLRClient``
and exposes the subset Dossier needs. If it's not installed (or
``DOSSIER_USE_STUB=1`` is set), a stub implementation takes over so the
document-ingest and wiki paths stay testable.

The stub is a **fake, not a mock** — it has the same return shape as HMLR
and persists state in memory so integration tests behave consistently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass
class HMLRResponse:
    """Shape of ``HMLRClient.chat()`` return value.

    Mirrors the real HMLR v0.1.2 dict-return shape so call sites don't branch.
    """

    content: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HMLREngine(Protocol):
    """Surface Dossier uses from an HMLR engine."""

    async def chat(self, message: str, session_id: str = "default_session") -> HMLRResponse: ...
    def get_memory_stats(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


class _RealHMLRAdapter:
    """Thin wrapper over ``hmlr.HMLRClient``."""

    def __init__(self, *, api_key: str | None, db_path: str):
        from hmlr import HMLRClient  # type: ignore[import-not-found]

        self._client = HMLRClient(api_key=api_key, db_path=db_path)

    async def chat(self, message: str, session_id: str = "default_session") -> HMLRResponse:
        result = await self._client.chat(message, session_id=session_id)
        return HMLRResponse(
            content=result.get("content", ""),
            status=result.get("status", "ok"),
            metadata=result.get("metadata", {}),
        )

    def get_memory_stats(self) -> dict[str, Any]:
        return self._client.get_memory_stats()

    def close(self) -> None:
        self._client.close()


class _StubHMLRAdapter:
    """In-memory stand-in for HMLR. Fake, not mock.

    Echoes the user message with a deterministic prefix, remembers the last
    few turns per session, and reports sane stats. Used when ``hmlr`` is not
    installed or ``DOSSIER_USE_STUB=1``.
    """

    def __init__(self) -> None:
        self._turns: dict[str, list[dict[str, str]]] = {}

    async def chat(self, message: str, session_id: str = "default_session") -> HMLRResponse:
        turns = self._turns.setdefault(session_id, [])
        turns.append({"role": "user", "content": message})
        reply = f"[stub] heard you say: {message!r}. {len(turns)} turns so far."
        turns.append({"role": "assistant", "content": reply})
        return HMLRResponse(
            content=reply,
            status="ok",
            metadata={"stub": True, "turns_in_session": len(turns)},
        )

    def get_memory_stats(self) -> dict[str, Any]:
        return {
            "backend": "stub",
            "sessions": len(self._turns),
            "total_turns": sum(len(t) for t in self._turns.values()),
        }

    def close(self) -> None:  # pragma: no cover — nothing to close
        self._turns.clear()


def build_engine(*, db_path: str, api_key: str | None = None, force_stub: bool = False) -> HMLREngine:
    """Return a real or stub engine, depending on availability and flags."""
    if force_stub:
        log.info("dossier: forcing HMLR stub adapter (force_stub=True)")
        return _StubHMLRAdapter()
    try:
        return _RealHMLRAdapter(api_key=api_key, db_path=db_path)
    except ImportError:
        log.info("dossier: hmlr not installed — using stub adapter")
        return _StubHMLRAdapter()
    except Exception as e:  # pragma: no cover — defensive for missing env vars etc.
        log.warning("dossier: HMLRClient init failed (%s) — falling back to stub", e)
        return _StubHMLRAdapter()
