"""Shared fixtures for Dossier tests.

Every test that touches the wiki gets a fresh ``tmp_path``-rooted project
via ``dossier_project``. No shared global state between tests.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from dossier.config import DossierConfig
from dossier.storage import BridgeBlockStore, FactStore


@pytest.fixture
def dossier_project(tmp_path: Path) -> DossierConfig:
    cfg = DossierConfig.for_root(tmp_path)
    cfg.ensure_dirs()
    # seed minimal index + log so writers can patch them
    (cfg.wiki_dir / "index.md").write_text(
        "---\nkind: index\nlast_updated: 2026-04-24\n---\n\n# Wiki index\n",
        encoding="utf-8",
    )
    (cfg.wiki_dir / "log.md").write_text(
        "---\nkind: log\nlast_updated: 2026-04-24\n---\n\n# Activity log\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def fact_store(dossier_project: DossierConfig) -> FactStore:
    return FactStore(dossier_project.facts_db)


@pytest.fixture
def bridge_store() -> BridgeBlockStore:
    return BridgeBlockStore()


@pytest.fixture
def sample_raw_file(dossier_project: DossierConfig) -> Path:
    """A raw/ file with enough content to exercise Scribe + FactScrubber."""
    path = dossier_project.raw_dir / f"{_dt.date.today().isoformat()}_alice_sample.md"
    path.write_text(
        """# Alice and the vegetarian constraint

Alice is a vegetarian. She prefers Mediterranean cuisine and avoids red meat.

Bob is Alice's colleague. Bob uses Python for data science.

The team's vegetarian policy is that all catered lunches must have at least
two vegetarian options. This is an invariant, not a preference.
""",
        encoding="utf-8",
    )
    return path
