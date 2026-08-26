import json
from pathlib import Path

from execweave.fidelity import FidelityAccumulator, derive_fidelity
from execweave.graph import GraphAccumulator, build_execution_graph


def _event(
    *,
    sequence: int,
    event_type: str,
    relation: str,
    backend: str,
    attribution: str | None,
    source_type: str = "process",
    target_type: str = "file",
) -> dict[str, object]:
    attributes: dict[str, object] = {"backend": backend, "causal": True}
    if attribution is not None:
        attributes["attribution"] = attribution
    return {
        "schema_version": "0.2",
        "event_id": f"event-{sequence}",
        "session_id": "s1",
        "timestamp": f"2026-08-26T00:00:{sequence:02d}Z",
        "sequence": sequence,
        "event_type": event_type,
        "relation": relation,
        "source": {
            "id": f"{source_type}:source",
            "type": source_type,
            "attributes": {"backend": backend},
        },
        "target": {
            "id": f"{target_type}:target",
            "type": target_type,
            "attributes": {},
        },
        "attributes": attributes,
    }


def test_portable_fidelity_is_sampled_without_lowering_behavior_severity() -> None:
    events = [
        _event(
            sequence=1,
            event_type="process.started",
            relation="LAUNCHED",
            backend="portable",
            attribution="polling",
            source_type="session",
            target_type="process",
        ),
        _event(
            sequence=2,
            event_type="network.connection",
            relation="CONNECTED_TO",
            backend="portable",
            attribution="process_polling",
            source_type="process",
            target_type="network_endpoint",
        ),
        _event(
            sequence=3,
            event_type="filesystem.modified",
            relation="OBSERVED_FILE_CHANGE",
            backend="portable",
            attribution="session_observation",
            source_type="session",
            target_type="file",
        ),
    ]

    fidelity = derive_fidelity(events)

    assert fidelity["session_id"] == "s1"
    assert fidelity["observed_process_count"] == 1
    assert fidelity["sampled_evidence_present"] is True
    assert fidelity["attribution_modes"]["process"] == ["process_polled"]
    assert fidelity["attribution_modes"]["filesystem"] == ["session_correlated"]
    assert "short_lived_process_capture" in fidelity["claims_not_supported"]
    assert "process_attributed_file_access" in fidelity["claims_not_supported"]
    assert "process_attributed_network" in fidelity["claims_supported"]
    assert "byte_level_dataflow" in fidelity["claims_not_supported"]
    assert "tamper_evident_evidence" in fidelity["claims_not_supported"]
    assert "severity" not in fidelity


def test_session_correlated_evidence_is_not_automatically_sampled() -> None:
    event = _event(
        sequence=1,
        event_type="semantic.tool_call",
        relation="CALLED_TOOL",
        backend="claude_hook",
        attribution=None,
        source_type="agent",
        target_type="tool_call",
    )

    fidelity = derive_fidelity([event])

    assert fidelity["attribution_modes"]["specialized"] == ["session_correlated"]
    assert fidelity["sampled_evidence_present"] is False


def test_network_attempt_is_part_of_network_attribution_contract() -> None:
    event = _event(
        sequence=1,
        event_type="network.connection_attempt",
        relation="CONNECT_ATTEMPTED",
        backend="strace",
        attribution="syscall",
        source_type="process",
        target_type="network_endpoint",
    )

    fidelity = derive_fidelity([event])

    assert fidelity["attribution_modes"]["network"] == ["syscall_attributed"]
    assert "process_attributed_network" in fidelity["claims_supported"]


def test_syscall_fidelity_records_stronger_attribution_without_claiming_complete_visibility() -> None:
    events = [
        _event(
            sequence=1,
            event_type="process.started",
            relation="SPAWNED",
            backend="strace",
            attribution="syscall",
            target_type="process",
        ),
        _event(
            sequence=2,
            event_type="filesystem.modified",
            relation="WROTE",
            backend="strace",
            attribution="syscall",
        ),
        _event(
            sequence=3,
            event_type="network.connection",
            relation="CONNECTED_TO",
            backend="strace",
            attribution="syscall",
            target_type="network_endpoint",
        ),
    ]

    fidelity = derive_fidelity(events)

    assert fidelity["sampled_evidence_present"] is False
    assert fidelity["attribution_modes"]["process"] == ["syscall_attributed"]
    assert "short_lived_process_capture" in fidelity["claims_supported"]
    assert "process_attributed_file_access" in fidelity["claims_supported"]
    assert "process_attributed_network" in fidelity["claims_supported"]
    assert "complete_process_tree" in fidelity["claims_not_supported"]
    assert "byte_level_dataflow" in fidelity["claims_not_supported"]
    assert any("not OS-wide visibility" in item for item in fidelity["limitations"])


def test_unresolved_process_reference_does_not_invent_missed_process_count() -> None:
    event = _event(
        sequence=1,
        event_type="process.started",
        relation="SPAWNED",
        backend="portable",
        attribution="polling",
        source_type="process_reference",
        target_type="process",
    )
    source = event["source"]
    assert isinstance(source, dict)
    source["attributes"] = {"unresolved": True}

    fidelity = derive_fidelity([event])

    assert fidelity["unresolved_process_references"] == 1
    assert fidelity["missed_process_lower_bound"] is None
    assert any("incomplete parentage resolution" in item for item in fidelity["limitations"])
    assert any("not a count of missed processes" in item for item in fidelity["limitations"])


def test_graph_accumulator_embeds_live_fidelity() -> None:
    accumulator = GraphAccumulator(session_id="s1", source_path="events.jsonl")
    accumulator.apply(
        _event(
            sequence=1,
            event_type="process.started",
            relation="LAUNCHED",
            backend="portable",
            attribution="polling",
            source_type="session",
            target_type="process",
        )
    )

    payload = accumulator.to_dict()

    assert payload["fidelity"]["fidelity_schema_version"] == "0.1"
    assert payload["fidelity"]["session_id"] == "s1"
    assert payload["fidelity"]["sampled_evidence_present"] is True


def test_final_graph_embeds_fidelity_block(tmp_path: Path) -> None:
    events = [
        {
            "schema_version": "0.2",
            "event_id": "start",
            "session_id": "s1",
            "timestamp": "2026-08-26T00:00:00Z",
            "sequence": 1,
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": {"id": "agent:test", "type": "agent"},
            "target": {
                "id": "session:s1",
                "type": "session",
                "attributes": {"backend": "portable"},
            },
            "attributes": {"backend": "portable"},
        },
        {
            "schema_version": "0.2",
            "event_id": "finish",
            "session_id": "s1",
            "timestamp": "2026-08-26T00:00:01Z",
            "sequence": 2,
            "event_type": "session.finished",
            "relation": "FINISHED_SESSION",
            "source": {"id": "session:s1", "type": "session"},
            "target": None,
            "attributes": {"backend": "portable"},
        },
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    graph = build_execution_graph(path).to_dict()

    assert graph["fidelity"]["fidelity_schema_version"] == "0.1"
    assert graph["fidelity"]["session_id"] == "s1"
    assert graph["fidelity"]["backend_observed"] == ["portable"]
    assert "byte_level_dataflow" in graph["fidelity"]["claims_not_supported"]


def test_fidelity_accumulator_is_bounded_summary() -> None:
    accumulator = FidelityAccumulator()
    for sequence in range(1, 101):
        accumulator.observe(
            _event(
                sequence=sequence,
                event_type="network.connection",
                relation="CONNECTED_TO",
                backend="portable",
                attribution="process_polling",
                target_type="network_endpoint",
            )
        )

    payload = accumulator.to_dict()

    assert payload["event_count"] == 100
    assert payload["attribution_modes"]["network"] == ["process_polled"]
