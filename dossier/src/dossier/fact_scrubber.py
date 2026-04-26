"""FactScrubber — extracts key-value claims into the fact store.

Looks for assertions of the form ``<subject> <verb> <value>`` where the verb
is one of a small closed set (``is``, ``has``, ``uses``, ``prefers``, etc).
The real HMLR FactScrubber is LLM-backed; this heuristic version is what
runs when HMLR isn't installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dossier.chunk_engine import Chunk
from dossier.storage import FactStore


@dataclass
class ExtractedFact:
    subject: str
    predicate: str
    value: str
    evidence: str


_FACT_RE = re.compile(
    r"\b([A-Z][\w ]{1,40}?)\s+"
    r"(is|was|has|had|uses|prefers|owns|avoids|cannot|must|requires)\s+"
    r"([^.!?\n]{1,120})"
)


class FactScrubber:
    def __init__(self, store: FactStore, *, source: str | None = None):
        self._store = store
        self._source = source

    def scrub(self, chunks: list[Chunk]) -> list[ExtractedFact]:
        found: list[ExtractedFact] = []
        for chunk in chunks:
            for match in _FACT_RE.finditer(chunk.text):
                subject, predicate, value = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
                fact = ExtractedFact(
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    evidence=match.group(0),
                )
                found.append(fact)
                key = f"{_slugify(subject)}.{predicate}"
                self._store.put(
                    key,
                    value,
                    confidence="medium",
                    source=self._source or chunk.source,
                )
        return found


def _slugify(text: str) -> str:
    out = []
    prev_dash = False
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("_")
            prev_dash = True
    return "".join(out).strip("_")
