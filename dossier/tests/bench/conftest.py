"""Pytest config for the bench suite — adds a ``--run-bench`` opt-in flag.

Bench tests cost real money (LLM calls) and take minutes. They only run
when the user passes ``--run-bench`` AND has an OpenAI key in the
environment. Otherwise they're skipped at collection time.
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-bench",
        action="store_true",
        default=False,
        help="Run bench tests that require an OpenAI key and take minutes",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-bench"):
        # also require the key at run time — fail loud, don't silently skip
        if not os.environ.get("OPENAI_API_KEY"):
            skip = pytest.mark.skip(reason="--run-bench set but OPENAI_API_KEY not in env")
            for item in items:
                if "bench" in item.keywords:
                    item.add_marker(skip)
        return
    skip = pytest.mark.skip(reason="bench tests need --run-bench (cost real money)")
    for item in items:
        if "bench" in item.keywords:
            item.add_marker(skip)
