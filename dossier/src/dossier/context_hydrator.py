"""Assembles the final prompt from lattice candidates.

Takes (question, filtered candidates) and returns a string ready to feed the
LLM. Inline citations use the form ``[entities/alice]`` so the LLM can quote
them back verbatim and callers can link straight to the wiki page.
"""

from __future__ import annotations

from dataclasses import dataclass

from dossier.lattice_crawler import Candidate


@dataclass
class HydratedContext:
    prompt: str
    citations: list[str]


DEFAULT_SYSTEM = (
    "You are answering using the Dossier memory lattice. Cite every non-trivial "
    "claim with the page reference in square brackets, e.g. [entities/alice] or "
    "[raw/2026-04-24_article.md]. If the lattice does not support a claim, say so "
    "rather than inventing."
)


class ContextHydrator:
    def __init__(self, *, system: str = DEFAULT_SYSTEM):
        self._system = system

    def hydrate(self, question: str, candidates: list[Candidate]) -> HydratedContext:
        lines = [self._system, "", "## Retrieved context", ""]
        citations: list[str] = []
        for c in candidates:
            ref = self._format_ref(c)
            citations.append(ref)
            lines.append(f"- **{ref}** — {c.text}")
        lines += ["", "## Question", "", question]
        return HydratedContext(prompt="\n".join(lines), citations=citations)

    def _format_ref(self, c: Candidate) -> str:
        if c.kind == "wiki":
            return c.ref.removesuffix(".md")
        if c.kind == "fact":
            return f"fact:{c.ref}"
        if c.kind == "bridge":
            return f"bridge:{c.ref}"
        return c.ref
