"""Retrieval over the memory lattice.

Dossier's lattice has three stores (see ``concepts/memory_lattice.md``):
wiki pages, fact store, bridge blocks. This module walks all three and
returns candidates for the Governor's Key 2 filter.

The vector path defers to HMLR when the embeddings extra is installed; the
stub path uses BM25-ish token overlap, which is plenty for the MVP spike
and for tests that don't want to pull in sentence-transformers.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dossier import frontmatter as fm
from dossier.config import DossierConfig
from dossier.storage import BridgeBlockStore, FactStore


@dataclass
class Candidate:
    kind: str  # 'wiki' | 'fact' | 'bridge'
    ref: str
    text: str
    score: float


class LatticeCrawler:
    def __init__(
        self,
        cfg: DossierConfig,
        fact_store: FactStore,
        bridge_blocks: BridgeBlockStore,
    ):
        self._cfg = cfg
        self._facts = fact_store
        self._bridges = bridge_blocks

    def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        query_tokens = _tokenise(query)
        if not query_tokens:
            return []
        candidates: list[Candidate] = []
        candidates.extend(self._search_wiki(query_tokens))
        candidates.extend(self._lookup_facts(query_tokens))
        candidates.extend(self._read_bridges(query_tokens))
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    def _search_wiki(self, query_tokens: Counter[str]) -> list[Candidate]:
        out: list[Candidate] = []
        for path in _iter_wiki_pages(self._cfg.wiki_dir):
            try:
                page = fm.loads(path.read_text(encoding="utf-8"))
            except fm.FrontmatterError:
                continue
            page_tokens = _tokenise(page.name + " " + page.body)
            score = _overlap(query_tokens, page_tokens)
            if score <= 0:
                continue
            rel = path.relative_to(self._cfg.wiki_dir).as_posix()
            excerpt = page.body.strip().splitlines()[0][:240] if page.body.strip() else page.name
            out.append(Candidate(kind="wiki", ref=rel, text=excerpt, score=score))
        return out

    def _lookup_facts(self, query_tokens: Counter[str]) -> list[Candidate]:
        out: list[Candidate] = []
        for fact in self._facts.all():
            key_tokens = _tokenise(fact.key.replace(".", " ").replace("_", " "))
            score = _overlap(query_tokens, key_tokens)
            if score <= 0:
                continue
            out.append(
                Candidate(
                    kind="fact",
                    ref=fact.key,
                    text=f"{fact.key} = {fact.value!r}",
                    score=score,
                )
            )
        return out

    def _read_bridges(self, query_tokens: Counter[str]) -> list[Candidate]:
        out: list[Candidate] = []
        for block in self._bridges.all():
            block_text = block.topic + " " + " ".join(t.get("content", "") for t in block.turns)
            tokens = _tokenise(block_text)
            score = _overlap(query_tokens, tokens)
            if score <= 0:
                continue
            out.append(
                Candidate(
                    kind="bridge",
                    ref=block.session_id,
                    text=block.topic,
                    score=score * 0.8,  # slight down-weight: short-term
                )
            )
        return out


_WORD_RE = re.compile(r"\b\w+\b")
_STOPWORDS = frozenset(
    "a an and the is are was were be been of to in on for with by that this these those it its "
    "as at or not but if then so do does did have has had i you he she we they me my your".split()
)


def _tokenise(text: str) -> Counter[str]:
    return Counter(
        t.lower() for t in _WORD_RE.findall(text) if t.lower() not in _STOPWORDS and len(t) > 1
    )


def _overlap(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    return float(sum((a & b).values()))


def _iter_wiki_pages(wiki_dir: Path):
    for sub in ("entities", "concepts", "sources"):
        d = wiki_dir / sub
        if not d.exists():
            continue
        yield from sorted(d.glob("*.md"))
