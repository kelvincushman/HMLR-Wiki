import datetime as _dt

from dossier import frontmatter as fm
from dossier.config import DossierConfig
from dossier.gardener import Gardener


def _write_page(cfg: DossierConfig, kind: str, name: str, body: str, **kwargs) -> None:
    page = fm.Page(kind=kind, name=name, body=body, **kwargs)
    sub = {"entity": cfg.entities_dir, "concept": cfg.concepts_dir, "source": cfg.sources_dir}[kind]
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{name.lower().replace(' ', '_')}.md").write_text(fm.dumps(page), encoding="utf-8")


def test_regenerates_index_from_pages(dossier_project: DossierConfig):
    _write_page(dossier_project, "entity", "alice", "A.\n")
    _write_page(dossier_project, "concept", "vegetarian_policy", "P.\n")
    report = Gardener(dossier_project).run()
    assert report.index_regenerated
    index_text = (dossier_project.wiki_dir / "index.md").read_text(encoding="utf-8")
    assert "alice" in index_text.lower()
    assert "vegetarian" in index_text.lower()
    assert "## Entities" in index_text
    assert "## Concepts" in index_text


def test_detects_orphans(dossier_project: DossierConfig):
    _write_page(dossier_project, "entity", "alice", "body\n")
    _write_page(dossier_project, "entity", "bob", "body\n")
    # nobody links to anything → both orphans
    report = Gardener(dossier_project).run()
    assert {o.split("/")[-1] for o in report.orphans} >= {"alice.md", "bob.md"}


def test_does_not_flag_stale_when_fresh(dossier_project: DossierConfig):
    _write_page(
        dossier_project,
        "entity",
        "alice",
        "body",
        confidence="low",
        last_updated=_dt.date.today(),
    )
    report = Gardener(dossier_project).run()
    assert "entities/alice.md" not in report.stale


def test_flags_stale_low_confidence_old_page(dossier_project: DossierConfig):
    old = _dt.date.today() - _dt.timedelta(days=200)
    _write_page(dossier_project, "entity", "alice", "body", confidence="low", last_updated=old)
    report = Gardener(dossier_project).run()
    assert "entities/alice.md" in report.stale


def test_flags_review_marker(dossier_project: DossierConfig):
    _write_page(dossier_project, "entity", "alice", "disputed section [[REVIEW]]\n")
    report = Gardener(dossier_project).run()
    assert "entities/alice.md" in report.review_flagged


def test_gardener_appends_to_log(dossier_project: DossierConfig):
    _write_page(dossier_project, "entity", "alice", "body\n")
    Gardener(dossier_project).run()
    log_text = (dossier_project.wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "gardener pass" in log_text
