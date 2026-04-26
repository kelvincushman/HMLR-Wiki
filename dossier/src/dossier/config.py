"""Runtime configuration for a Dossier project."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DossierConfig:
    """Resolved paths and toggles for one Dossier project.

    The default ``root`` resolution walks up from cwd looking for a directory
    that contains ``wiki/`` and ``raw/``. If nothing matches, cwd is used.
    """

    root: Path
    raw_dir: Path
    wiki_dir: Path
    hmlr_dir: Path
    facts_db: Path
    use_stub: bool = False
    hmlr_model: str = "gpt-4.1-mini"
    confidence_stale_threshold_days: int = 90

    sources_dir: Path = field(init=False)
    entities_dir: Path = field(init=False)
    concepts_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True still lets us set via object.__setattr__
        object.__setattr__(self, "sources_dir", self.wiki_dir / "sources")
        object.__setattr__(self, "entities_dir", self.wiki_dir / "entities")
        object.__setattr__(self, "concepts_dir", self.wiki_dir / "concepts")

    @classmethod
    def discover(cls, start: Path | None = None) -> DossierConfig:
        root = _find_project_root(start or Path.cwd())
        return cls.for_root(root)

    @classmethod
    def for_root(cls, root: Path) -> DossierConfig:
        root = root.resolve()
        return cls(
            root=root,
            raw_dir=root / "raw",
            wiki_dir=root / "wiki",
            hmlr_dir=root / ".hmlr",
            facts_db=root / ".hmlr" / "facts.db",
            use_stub=os.environ.get("DOSSIER_USE_STUB", "0") == "1",
            hmlr_model=os.environ.get("DOSSIER_MODEL", "gpt-4.1-mini"),
        )

    def ensure_dirs(self) -> None:
        for d in (
            self.raw_dir,
            self.wiki_dir,
            self.sources_dir,
            self.entities_dir,
            self.concepts_dir,
            self.hmlr_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def _find_project_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "wiki").is_dir() and (candidate / "raw").is_dir():
            return candidate
    return start
