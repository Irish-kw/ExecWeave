from execweave.schema import Entity, RuntimeEvent


def test_runtime_event_is_graph_ready() -> None:
    source = Entity(type="process", id="process:1")
    target = Entity(type="file", id="file:/tmp/a")
    event = RuntimeEvent.create(
        session_id="s",
        event_type="filesystem.open",
        relation="OPENED_READ",
        source=source,
        target=target,
    )
    payload = event.to_dict()
    assert payload["source"]["id"] == "process:1"
    assert payload["relation"] == "OPENED_READ"
    assert payload["target"]["id"] == "file:/tmp/a"
    assert payload["schema_version"] == "0.2"
