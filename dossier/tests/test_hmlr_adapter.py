import pytest

from dossier.hmlr_adapter import HMLRResponse, build_engine


@pytest.mark.asyncio
async def test_stub_echoes_and_tracks_turn_count():
    engine = build_engine(db_path=":memory:", force_stub=True)
    try:
        r1 = await engine.chat("hello", session_id="s")
        r2 = await engine.chat("world", session_id="s")
        assert isinstance(r1, HMLRResponse)
        assert r1.metadata["stub"] is True
        assert r2.metadata["turns_in_session"] == 4  # 2 user + 2 assistant
    finally:
        engine.close()


@pytest.mark.asyncio
async def test_stub_sessions_are_isolated():
    engine = build_engine(db_path=":memory:", force_stub=True)
    try:
        await engine.chat("hi", session_id="a")
        r = await engine.chat("hi", session_id="b")
        assert r.metadata["turns_in_session"] == 2
    finally:
        engine.close()


def test_stub_stats():
    engine = build_engine(db_path=":memory:", force_stub=True)
    try:
        stats = engine.get_memory_stats()
        assert stats["backend"] == "stub"
    finally:
        engine.close()
