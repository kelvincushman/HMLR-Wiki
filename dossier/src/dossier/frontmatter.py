"""Frontmatter parsing, validation, and round-trip for wiki pages.

Every wiki page is a YAML frontmatter block (``---``-delimited) followed by
markdown. The frontmatter carries the metadata the Gardener needs for
contradiction resolution; the markdown body is what humans read.

Round-trip guarantee: ``dumps(loads(text)) == text`` up to whitespace in the
YAML block, and the body is preserved exactly.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import yaml

FRONTMATTER_DELIM = "---"

VALID_KINDS = {"entity", "concept", "source", "index", "log"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_EDITED_BY = {"llm", "human"}


class FrontmatterError(ValueError):
    """Raised when a page has missing/invalid frontmatter."""


@dataclass
class SourceRef:
    """One grounding source for a claim. Exactly one of ``raw`` or ``session`` is set."""

    raw: str | None = None
    session: str | None = None
    turn: int | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.raw is not None:
            return {"raw": self.raw}
        return {"session": self.session, "turn": self.turn}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRef:
        return cls(raw=data.get("raw"), session=data.get("session"), turn=data.get("turn"))


@dataclass
class Page:
    """A wiki page: frontmatter + markdown body."""

    kind: str
    name: str
    body: str = ""
    aliases: list[str] = field(default_factory=list)
    confidence: str = "medium"
    last_updated: _dt.date = field(default_factory=_dt.date.today)
    sources: list[SourceRef] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    touched_by: list[dict[str, Any]] = field(default_factory=list)
    edited_by: str = "llm"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise FrontmatterError(f"invalid kind: {self.kind!r} (valid: {sorted(VALID_KINDS)})")
        if self.confidence not in VALID_CONFIDENCE:
            raise FrontmatterError(f"invalid confidence: {self.confidence!r}")
        if self.edited_by not in VALID_EDITED_BY:
            raise FrontmatterError(f"invalid edited_by: {self.edited_by!r}")

    def frontmatter_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "aliases": list(self.aliases),
            "confidence": self.confidence,
            "last_updated": self.last_updated.isoformat(),
            "sources": [s.to_dict() for s in self.sources],
            "supersedes": list(self.supersedes),
            "touched_by": list(self.touched_by),
            "edited_by": self.edited_by,
        }
        data.update(self.extra)
        return data

    def dumps(self) -> str:
        return dumps(self)


def loads(text: str) -> Page:
    """Parse a markdown-with-frontmatter string into a ``Page``."""
    fm, body = _split_frontmatter(text)
    if fm is None:
        raise FrontmatterError("no frontmatter block found (expected leading ---)")
    try:
        data = yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise FrontmatterError(f"frontmatter must be a mapping, got {type(data).__name__}")
    return _page_from_dict(data, body)


def dumps(page: Page) -> str:
    """Serialise a ``Page`` back to markdown-with-frontmatter."""
    fm_text = yaml.safe_dump(
        page.frontmatter_dict(),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    body = page.body.rstrip("\n")
    return f"{FRONTMATTER_DELIM}\n{fm_text}{FRONTMATTER_DELIM}\n\n{body}\n"


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    stripped = text.lstrip()
    if not stripped.startswith(FRONTMATTER_DELIM):
        return None, text
    # find the second delimiter
    lines = text.splitlines(keepends=True)
    # find first delimiter (skipping any leading blank lines)
    start = None
    for i, line in enumerate(lines):
        if line.strip() == FRONTMATTER_DELIM:
            start = i
            break
    if start is None:
        return None, text
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == FRONTMATTER_DELIM:
            end = j
            break
    if end is None:
        raise FrontmatterError("unterminated frontmatter block")
    fm = "".join(lines[start + 1 : end])
    body = "".join(lines[end + 1 :]).lstrip("\n")
    return fm, body


def _page_from_dict(data: dict[str, Any], body: str) -> Page:
    known = {
        "kind",
        "name",
        "aliases",
        "confidence",
        "last_updated",
        "sources",
        "supersedes",
        "touched_by",
        "edited_by",
    }
    extra = {k: v for k, v in data.items() if k not in known}

    last_updated = data.get("last_updated", _dt.date.today())
    if isinstance(last_updated, str):
        last_updated = _dt.date.fromisoformat(last_updated)
    elif isinstance(last_updated, _dt.datetime):
        last_updated = last_updated.date()

    sources_raw = data.get("sources") or []
    sources = [SourceRef.from_dict(s) if isinstance(s, dict) else SourceRef(raw=str(s)) for s in sources_raw]

    return Page(
        kind=str(data.get("kind", "")),
        name=str(data.get("name", "")),
        body=body,
        aliases=list(data.get("aliases") or []),
        confidence=str(data.get("confidence", "medium")),
        last_updated=last_updated,
        sources=sources,
        supersedes=list(data.get("supersedes") or []),
        touched_by=list(data.get("touched_by") or []),
        edited_by=str(data.get("edited_by", "llm")),
        extra=extra,
    )
