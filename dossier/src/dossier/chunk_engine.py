"""Chunking + embedding hook point.

HMLR has a first-class chunking module at ``hmlr.memory.chunking``. When the
real engine is present, defer to it. Otherwise use a cheap paragraph-split
that keeps the wiki path usable without embedding models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    source: str
    ordinal: int
    text: str
    char_span: tuple[int, int]


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def chunk_text(text: str, *, source: str, target_chars: int = 1200) -> list[Chunk]:
    """Paragraph-level chunker with a target character budget per chunk."""
    chunks: list[Chunk] = []
    cursor = 0
    buffer: list[str] = []
    buf_start = 0

    for para in _iter_paragraphs(text):
        para_text, para_start, para_end = para
        if not buffer:
            buf_start = para_start
        buffer.append(para_text)
        current_len = sum(len(p) for p in buffer) + 2 * (len(buffer) - 1)
        if current_len >= target_chars:
            joined = "\n\n".join(buffer)
            chunks.append(
                Chunk(source=source, ordinal=len(chunks), text=joined, char_span=(buf_start, para_end))
            )
            buffer.clear()
        cursor = para_end

    if buffer:
        joined = "\n\n".join(buffer)
        chunks.append(
            Chunk(source=source, ordinal=len(chunks), text=joined, char_span=(buf_start, cursor))
        )
    return chunks


def chunk_file(path: Path) -> list[Chunk]:
    text = Path(path).read_text(encoding="utf-8")
    return chunk_text(text, source=str(path))


def _iter_paragraphs(text: str):
    # yields (paragraph_text, start_char, end_char)
    pos = 0
    for match in _PARAGRAPH_SPLIT.finditer(text):
        end = match.start()
        para = text[pos:end]
        if para.strip():
            yield para, pos, end
        pos = match.end()
    tail = text[pos:]
    if tail.strip():
        yield tail, pos, len(text)
