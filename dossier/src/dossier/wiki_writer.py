"""Writes markdown wiki pages with the contradiction-resolution policy applied.

All mutations flow through this module. The policy (SCHEMA.md): newer wins
unless the older page is ``confidence: high``; ties flag ``[[REVIEW]]`` and
do not overwrite.

File writes are atomic (temp file + rename) so a partial write never leaves
a page in an unparseable state.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from slugify import slugify as _slugify

from dossier import frontmatter as fm
from dossier.config import DossierConfig


@dataclass
class WriteResult:
    path: Path
    created: bool
    superseded: bool
    review_flagged: bool


class WikiWriter:
    def __init__(self, cfg: DossierConfig):
        self._cfg = cfg
        self._cfg.ensure_dirs()

    # --- filename / path helpers ------------------------------------------

    def slug(self, name: str) -> str:
        return _slugify(name, separator="_", max_length=60) or "untitled"

    def entity_path(self, name: str) -> Path:
        return self._cfg.entities_dir / f"{self.slug(name)}.md"

    def concept_path(self, name: str) -> Path:
        return self._cfg.concepts_dir / f"{self.slug(name)}.md"

    def source_path(self, raw_path: Path, ingested_on: _dt.date | None = None) -> Path:
        date = (ingested_on or _dt.date.today()).isoformat()
        return self._cfg.sources_dir / f"{date}_{self.slug(raw_path.stem)}.md"

    # --- writers -----------------------------------------------------------

    def upsert_entity(
        self,
        name: str,
        *,
        body: str,
        source: fm.SourceRef,
        aliases: list[str] | None = None,
        confidence: str = "medium",
    ) -> WriteResult:
        path = self.entity_path(name)
        return self._upsert(
            path,
            kind="entity",
            name=name,
            body=body,
            source=source,
            aliases=aliases or [],
            confidence=confidence,
        )

    def upsert_concept(
        self,
        name: str,
        *,
        body: str,
        source: fm.SourceRef,
        aliases: list[str] | None = None,
        confidence: str = "medium",
    ) -> WriteResult:
        path = self.concept_path(name)
        return self._upsert(
            path,
            kind="concept",
            name=name,
            body=body,
            source=source,
            aliases=aliases or [],
            confidence=confidence,
        )

    def write_source_summary(
        self,
        raw_path: Path,
        *,
        title: str,
        body: str,
        ingested_on: _dt.date | None = None,
    ) -> WriteResult:
        path = self.source_path(raw_path, ingested_on=ingested_on)
        page = fm.Page(
            kind="source",
            name=title,
            body=body,
            confidence="high",
            last_updated=ingested_on or _dt.date.today(),
            sources=[fm.SourceRef(raw=str(raw_path.name))],
        )
        created = not path.exists()
        _atomic_write(path, fm.dumps(page))
        return WriteResult(path=path, created=created, superseded=False, review_flagged=False)

    def append_log(self, message: str, *, date: _dt.date | None = None) -> None:
        log_path = self._cfg.wiki_dir / "log.md"
        today = (date or _dt.date.today()).isoformat()
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else _fresh_log()
        # insert under today's heading — create one if missing.
        heading = f"## {today}"
        if heading in existing:
            patched = re.sub(
                rf"({re.escape(heading)}\n)",
                rf"\1\n- {message}\n",
                existing,
                count=1,
            )
        else:
            # insert new heading after the frontmatter block
            fm_end = existing.find("---", 3)
            insert_at = existing.find("\n", fm_end) + 1 if fm_end != -1 else 0
            prefix = existing[:insert_at]
            suffix = existing[insert_at:]
            new_section = f"\n{heading}\n\n- {message}\n"
            patched = prefix + new_section + suffix
        _atomic_write(log_path, patched)

    # --- internal ----------------------------------------------------------

    def _upsert(
        self,
        path: Path,
        *,
        kind: str,
        name: str,
        body: str,
        source: fm.SourceRef,
        aliases: list[str],
        confidence: str,
    ) -> WriteResult:
        if not path.exists():
            page = fm.Page(
                kind=kind,
                name=name,
                body=body,
                aliases=aliases,
                confidence=confidence,
                sources=[source],
            )
            _atomic_write(path, fm.dumps(page))
            return WriteResult(path=path, created=True, superseded=False, review_flagged=False)

        existing = fm.loads(path.read_text(encoding="utf-8"))
        review = False
        superseded = False

        # apply contradiction-resolution policy
        if existing.confidence == "high" and confidence != "high":
            # existing wins — merge source, bump touched_by, keep body
            merged_body = existing.body
        elif _bodies_contradict(existing.body, body):
            if existing.confidence == confidence and existing.edited_by == "llm":
                # tie between LLM-written pages of equal confidence — flag
                merged_body = _flag_review(existing.body, body)
                review = True
            else:
                merged_body = body
                superseded = True
        else:
            merged_body = _append_section(existing.body, body)

        updated = fm.Page(
            kind=existing.kind,
            name=existing.name,
            body=merged_body,
            aliases=_merge_lists(existing.aliases, aliases),
            confidence=_max_confidence(existing.confidence, confidence),
            last_updated=_dt.date.today(),
            sources=_merge_sources(existing.sources, [source]),
            supersedes=existing.supersedes + ([existing.name] if superseded else []),
            touched_by=existing.touched_by + [source.to_dict()],
            edited_by=existing.edited_by if existing.edited_by == "human" else "llm",
            extra=existing.extra,
        )
        _atomic_write(path, fm.dumps(updated))
        return WriteResult(path=path, created=False, superseded=superseded, review_flagged=review)


# --- helpers ---------------------------------------------------------------

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def _max_confidence(a: str, b: str) -> str:
    return a if _CONFIDENCE_ORDER.get(a, 0) >= _CONFIDENCE_ORDER.get(b, 0) else b


def _merge_lists(a: list[str], b: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in a + b:
        key = item.lower() if isinstance(item, str) else item
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_sources(a: list[fm.SourceRef], b: list[fm.SourceRef]) -> list[fm.SourceRef]:
    seen = set()
    out: list[fm.SourceRef] = []
    for s in a + b:
        key = (s.raw, s.session, s.turn)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


_CONTRADICT_STOPWORDS = frozenset(
    "a an the is are was were be been being am of to in on for with by "
    "that this these those it its as at or not but never no cannot don't "
    "doesn't didn't won't wouldn't and do does did has have had".split()
)


def _bodies_contradict(old: str, new: str) -> bool:
    """Content-token contradiction detector.

    Compares two bodies by (a) polarity (does either carry a negation?) and
    (b) content-token overlap (shared nouns/verbs after stopwords removed).
    A contradiction fires when polarity differs *and* the shared content
    is substantial — i.e. both bodies are talking about the same thing
    but disagreeing on sign.
    """
    old_l = old.lower()
    new_l = new.lower()
    negations = ("not", "never", "cannot", "no ", "n't")
    old_neg = any(n in old_l for n in negations)
    new_neg = any(n in new_l for n in negations)
    if old_neg == new_neg:
        return False

    def _content_tokens(text: str) -> set[str]:
        tokens: set[str] = set()
        for raw in text.lower().split():
            cleaned = raw.strip(".,;:!?()[]\"'`")
            if cleaned.isalpha() and len(cleaned) > 2 and cleaned not in _CONTRADICT_STOPWORDS:
                tokens.add(cleaned)
        return tokens

    shared = _content_tokens(old) & _content_tokens(new)
    return len(shared) >= 2


def _flag_review(old: str, new: str) -> str:
    return (
        f"{old.rstrip()}\n\n"
        f"## [[REVIEW]] — conflicting claim\n\n"
        f"Later source added:\n\n> {new.strip()}\n\n"
        "Gardener flagged on contradiction; resolve this section manually.\n"
    )


def _append_section(old: str, new: str) -> str:
    return f"{old.rstrip()}\n\n{new.strip()}\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".dossier-", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _fresh_log() -> str:
    today = _dt.date.today().isoformat()
    return (
        f"---\n"
        f"kind: log\n"
        f"last_updated: {today}\n"
        f"---\n\n"
        "# Activity log\n\n"
        "Newest on top.\n"
    )
