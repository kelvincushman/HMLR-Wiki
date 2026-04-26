"""The Scribe — extracts entities and concepts, queues wiki-page updates.

Mirrors HMLR's Scribe agent but writes to markdown wiki pages instead of a
JSON user profile. On document ingest the Scribe identifies named things and
abstractions in the text; on dialogue it records what the user said about
them.

The real Scribe runs an LLM call. This module provides a pluggable protocol
so integration code can swap in an LLM-backed extractor without touching
the rest of the pipeline. The default extractor is heuristic — cheap and
deterministic for tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from dossier.chunk_engine import Chunk


@dataclass
class ExtractedEntity:
    name: str
    aliases: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # raw snippets supporting the mention


@dataclass
class ExtractedConcept:
    name: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class ScribeResult:
    entities: list[ExtractedEntity]
    concepts: list[ExtractedConcept]


class EntityExtractor(Protocol):
    def extract(self, chunks: list[Chunk]) -> ScribeResult: ...


class Scribe:
    """Default Scribe: uses a heuristic extractor. Wrap with your own for LLM-backed work."""

    def __init__(self, extractor: EntityExtractor | None = None) -> None:
        self._extractor = extractor or HeuristicExtractor()

    def process(self, chunks: list[Chunk]) -> ScribeResult:
        return self._extractor.extract(chunks)


# --- default extractor ---------------------------------------------------

_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_CONCEPT_TRIGGERS = (
    "policy", "constraint", "invariant", "principle", "rule",
    "decision", "framework", "approach", "pattern", "architecture",
)


class HeuristicExtractor:
    """Token-pattern extractor. Deliberately conservative; LLM extractor is better.

    - Entities: proper-noun phrases of 1-4 tokens, deduped case-insensitively.
    - Concepts: noun phrases that sit adjacent to a concept trigger word.
    """

    def extract(self, chunks: list[Chunk]) -> ScribeResult:
        entities: dict[str, ExtractedEntity] = {}
        concepts: dict[str, ExtractedConcept] = {}

        for chunk in chunks:
            for match in _PROPER_NOUN_RE.finditer(chunk.text):
                name = match.group(1)
                key = name.lower()
                entity = entities.setdefault(key, ExtractedEntity(name=name))
                evidence = _snippet(chunk.text, match.start(), match.end())
                if evidence not in entity.evidence:
                    entity.evidence.append(evidence)

            lowered = chunk.text.lower()
            for trigger in _CONCEPT_TRIGGERS:
                for idx in _find_all(lowered, trigger):
                    # take up to 4 words preceding the trigger as the concept name
                    before = chunk.text[max(0, idx - 60) : idx].rstrip()
                    tokens = before.split()
                    if not tokens:
                        continue
                    name = " ".join(tokens[-3:]).strip(",.;:")
                    if not name or name.lower() == trigger:
                        continue
                    key = name.lower()
                    concept = concepts.setdefault(key, ExtractedConcept(name=name))
                    evidence = _snippet(chunk.text, idx, idx + len(trigger))
                    if evidence not in concept.evidence:
                        concept.evidence.append(evidence)

        return ScribeResult(
            entities=list(entities.values()),
            concepts=list(concepts.values()),
        )


def _snippet(text: str, start: int, end: int, *, pad: int = 40) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    snippet = text[s:e].replace("\n", " ").strip()
    return ("..." if s > 0 else "") + snippet + ("..." if e < len(text) else "")


def _find_all(haystack: str, needle: str):
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return
        yield idx
        start = idx + len(needle)
