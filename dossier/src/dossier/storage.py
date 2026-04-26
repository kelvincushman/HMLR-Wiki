"""SQL fact store + in-memory bridge blocks.

The fact store is the fast path for exact key lookups on fast-changing state
(API key versions, counters, policy revisions). Wiki pages link *to* the fact
store rather than duplicating these values.

Bridge blocks hold the active-topic cache. They're short-lived: the Gardener
promotes stabilised blocks into wiki pages on each pass.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Fact:
    key: str
    value: Any
    updated_at: _dt.datetime
    confidence: str = "medium"
    source: str | None = None


class FactStore:
    """SQLite-backed key-value store with temporal supersession.

    Writes always overwrite — older rows are kept in ``fact_history`` so the
    Gardener can walk supersession chains.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confidence TEXT NOT NULL DEFAULT 'medium',
                    source TEXT
                );
                CREATE TABLE IF NOT EXISTS fact_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_fact_history_key ON fact_history(key);
                """
            )

    def put(
        self,
        key: str,
        value: Any,
        *,
        confidence: str = "medium",
        source: str | None = None,
    ) -> None:
        now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        value_text = json.dumps(value)
        with closing(self._connect()) as conn, conn:
            prior = conn.execute("SELECT * FROM facts WHERE key = ?", (key,)).fetchone()
            if prior is not None:
                conn.execute(
                    "INSERT INTO fact_history (key, value, updated_at, confidence, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (prior["key"], prior["value"], prior["updated_at"], prior["confidence"], prior["source"]),
                )
            conn.execute(
                "INSERT INTO facts (key, value, updated_at, confidence, source) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value, updated_at=excluded.updated_at, "
                "confidence=excluded.confidence, source=excluded.source",
                (key, value_text, now, confidence, source),
            )

    def get(self, key: str) -> Fact | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM facts WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return Fact(
            key=row["key"],
            value=json.loads(row["value"]),
            updated_at=_dt.datetime.fromisoformat(row["updated_at"]),
            confidence=row["confidence"],
            source=row["source"],
        )

    def history(self, key: str) -> list[Fact]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM fact_history WHERE key = ? ORDER BY id DESC",
                (key,),
            ).fetchall()
        return [
            Fact(
                key=r["key"],
                value=json.loads(r["value"]),
                updated_at=_dt.datetime.fromisoformat(r["updated_at"]),
                confidence=r["confidence"],
                source=r["source"],
            )
            for r in rows
        ]

    def all(self) -> list[Fact]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM facts ORDER BY key").fetchall()
        return [
            Fact(
                key=r["key"],
                value=json.loads(r["value"]),
                updated_at=_dt.datetime.fromisoformat(r["updated_at"]),
                confidence=r["confidence"],
                source=r["source"],
            )
            for r in rows
        ]


@dataclass
class BridgeBlock:
    """Short-term cache for the active topic of a dialogue session."""

    session_id: str
    topic: str
    turns: list[dict[str, Any]]
    opened_at: _dt.datetime
    entities_touched: set[str]
    concepts_touched: set[str]

    def touch_entity(self, name: str) -> None:
        self.entities_touched.add(name)

    def touch_concept(self, name: str) -> None:
        self.concepts_touched.add(name)


class BridgeBlockStore:
    """In-memory bridge-block store, keyed by session_id.

    Persistence across process restarts is delegated to HMLR when installed.
    For the stub path we keep it in-memory — fine for tests, fine for the spike.
    """

    def __init__(self) -> None:
        self._blocks: dict[str, BridgeBlock] = {}

    def open(self, session_id: str, topic: str) -> BridgeBlock:
        block = BridgeBlock(
            session_id=session_id,
            topic=topic,
            turns=[],
            opened_at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
            entities_touched=set(),
            concepts_touched=set(),
        )
        self._blocks[session_id] = block
        return block

    def active(self, session_id: str) -> BridgeBlock | None:
        return self._blocks.get(session_id)

    def close(self, session_id: str) -> BridgeBlock | None:
        return self._blocks.pop(session_id, None)

    def all(self) -> list[BridgeBlock]:
        return list(self._blocks.values())
