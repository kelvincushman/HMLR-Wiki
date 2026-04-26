"""Dossier — HMLR + LLM Wiki fusion.

A memory lattice where HMLR's state engine writes to human-readable markdown
instead of opaque SQL blobs. See ``SCHEMA.md`` and ``AGENTS.md`` at the project
root for the operating conventions.
"""

from dossier.config import DossierConfig
from dossier.governor import Governor, Route
from dossier.ingest import ingest_document
from dossier.query import query

__version__ = "0.1.0"

__all__ = [
    "DossierConfig",
    "Governor",
    "Route",
    "ingest_document",
    "query",
    "__version__",
]
