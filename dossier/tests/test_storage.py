from dossier.storage import BridgeBlockStore, FactStore


def test_fact_put_get_roundtrip(fact_store: FactStore):
    fact_store.put("alice.is", "vegetarian", confidence="high", source="raw/a.md")
    got = fact_store.get("alice.is")
    assert got is not None
    assert got.value == "vegetarian"
    assert got.confidence == "high"
    assert got.source == "raw/a.md"


def test_fact_overwrite_records_history(fact_store: FactStore):
    fact_store.put("api.version", 5, confidence="medium", source="s1")
    fact_store.put("api.version", 6, confidence="high", source="s2")
    current = fact_store.get("api.version")
    assert current is not None and current.value == 6
    history = fact_store.history("api.version")
    assert len(history) == 1
    assert history[0].value == 5
    assert history[0].source == "s1"


def test_fact_all_listing(fact_store: FactStore):
    fact_store.put("a", 1)
    fact_store.put("b", 2)
    keys = {f.key for f in fact_store.all()}
    assert keys == {"a", "b"}


def test_bridge_block_open_touch_close(bridge_store: BridgeBlockStore):
    block = bridge_store.open("sess-1", topic="vegetarianism")
    block.touch_entity("Alice")
    block.touch_concept("vegetarian policy")
    block.turns.append({"role": "user", "content": "hi"})
    assert bridge_store.active("sess-1") is block
    assert "Alice" in block.entities_touched
    closed = bridge_store.close("sess-1")
    assert closed is block
    assert bridge_store.active("sess-1") is None
