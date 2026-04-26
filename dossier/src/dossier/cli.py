"""Dossier CLI — thin wrapper over the ingest/query/gardener/chat paths."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import click

from dossier import __version__
from dossier.config import DossierConfig
from dossier.gardener import Gardener
from dossier.hmlr_adapter import build_engine
from dossier.ingest import ingest_document
from dossier.query import query as query_path


@click.group()
@click.version_option(__version__)
@click.option("--project", "project_root", type=click.Path(path_type=Path), default=None, help="Project root (defaults to discovery from cwd)")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def main(ctx: click.Context, project_root: Path | None, verbose: bool) -> None:
    """Dossier — HMLR + LLM Wiki fusion."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = DossierConfig.for_root(project_root) if project_root else DossierConfig.discover()
    ctx.obj = cfg


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_obj
def ingest(cfg: DossierConfig, source: Path) -> None:
    """Ingest a source file from raw/ (path can be absolute or relative)."""
    result = ingest_document(source, cfg=cfg)
    click.echo(f"routed: {result.route.value}")
    click.echo(f"facts: {result.facts_written}")
    for w in result.pages_written:
        state = "created" if w.created else ("superseded" if w.superseded else "updated")
        review = " [REVIEW]" if w.review_flagged else ""
        click.echo(f"  {state:<11} {w.path.relative_to(cfg.root)}{review}")


@main.command(name="query")
@click.argument("question", nargs=-1, required=True)
@click.option("--limit", type=int, default=10, show_default=True)
@click.option("--show-prompt", is_flag=True, help="Print the hydrated prompt")
@click.pass_obj
def query_cmd(cfg: DossierConfig, question: tuple[str, ...], limit: int, show_prompt: bool) -> None:
    """Query the lattice; prints candidates and (optionally) the hydrated prompt."""
    q = " ".join(question)
    result = query_path(q, cfg=cfg, limit=limit)
    click.echo(f"question: {q}")
    click.echo(f"candidates ({len(result.candidates)}):")
    for c in result.candidates:
        click.echo(f"  {c.kind:<6} {c.ref:<40} score={c.score:.2f}")
    if show_prompt:
        click.echo("\n--- hydrated prompt ---\n")
        click.echo(result.hydrated.prompt)


@main.command()
@click.pass_obj
def gardener(cfg: DossierConfig) -> None:
    """Run the gardener / lint pass."""
    report = Gardener(cfg).run()
    click.echo(f"gardener complete — {report.summary()}")
    if report.orphans:
        click.echo(f"  orphans: {', '.join(report.orphans)}")
    if report.stale:
        click.echo(f"  stale:   {', '.join(report.stale)}")
    if report.review_flagged:
        click.echo(f"  review:  {', '.join(report.review_flagged)}")


@main.command()
@click.option("--session", default="default_session", help="Session id")
@click.pass_obj
def chat(cfg: DossierConfig, session: str) -> None:
    """Interactive REPL. Requires the `hmlr` extra for real memory."""
    engine = build_engine(db_path=str(cfg.facts_db.parent / "memory.db"), force_stub=cfg.use_stub)
    click.echo("dossier chat — ctrl-D to exit.")
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                msg = click.prompt("you", prompt_suffix="> ", show_default=False).strip()
            except click.exceptions.Abort:
                click.echo()
                break
            except EOFError:
                break
            if not msg:
                continue
            response = loop.run_until_complete(engine.chat(msg, session_id=session))
            click.echo(f"dossier> {response.content}")
    finally:
        loop.close()
        engine.close()


@main.command()
@click.pass_obj
def doctor(cfg: DossierConfig) -> None:
    """Sanity-check the project layout and dependencies."""
    click.echo(f"root:       {cfg.root}")
    click.echo(f"raw:        {cfg.raw_dir} {'OK' if cfg.raw_dir.exists() else '(missing)'}")
    click.echo(f"wiki:       {cfg.wiki_dir} {'OK' if cfg.wiki_dir.exists() else '(missing)'}")
    click.echo(f"facts_db:   {cfg.facts_db}")
    try:
        import hmlr  # type: ignore[import-not-found]  # noqa: F401

        click.echo("hmlr:       installed")
    except ImportError:
        click.echo("hmlr:       not installed (stub adapter active)")
    click.echo(f"use_stub:   {cfg.use_stub}")
    click.echo(f"model:      {cfg.hmlr_model}")


if __name__ == "__main__":
    main(obj=None)
