from execweave.schema import Entity, RuntimeEvent


def test_runtime_event_is_graph_ready() -> None:
    source = Entity(type="process", id="process:1", name="agent")
    target = Entity(type="network_endpoint", id="endpoint:example.com:443", name="example.com:443")

    event = RuntimeEvent.create(
        session_id="session-1",
        event_type="network.connection",
        relation="CONNECTED_TO",
        source=source,
        target=target,
    )

    payload = event.to_dict()
    assert payload["schema_version"] == "0.1"
    assert payload["session_id"] == "session-1"
    assert payload["relation"] == "CONNECTED_TO"
    assert payload["source"]["id"] == "process:1"
    assert payload["target"]["id"] == "endpoint:example.com:443"
