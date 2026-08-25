import json
from pathlib import Path

import pytest

from execweave.graph import build_execution_graph, write_execution_graph
from execweave.schema import Entity, RuntimeEvent
from execweave.sink import JsonlSink


def _emit_complete_stream(path: Path) -> None:
    sink = JsonlSink(path)
    agent = Entity(type="agent", id="agent:test", name="test")
    session = Entity(type="session", id="session:s1", name="s1")
    process = Entity(type="process", id="process:s1:10", name="python")
    file = Entity(type="file", id="file:/tmp/a.txt", name="a.txt")

    sink.emit(
        RuntimeEvent.create(
            session_id="s1",
            event_type="session.started",
            relation="STARTED_SESSION",
            source=agent,
            target=session,
        )
    )
    sink.emit(
        RuntimeEvent.create(
            session_id="s1",
            event_type="process.started",
            relation="LAUNCHED",
            source=session,
            target=process,
            attributes={"backend": "strace", "attribution": "syscall", "causal": True},
        )
    )
    for _ in range(2):
        sink.emit(
            RuntimeEvent.create(
                session_id="s1",
                event_type="filesystem.open",
                relation="OPENED_READ",
                source=process,
                target=file,
                attributes={"backend": "strace", "attribution": "syscall", "causal": True},
            )
        )
    sink.emit(
        RuntimeEvent.create(
            session_id="s1",
            event_type="process.exited",
            relation="EXITED",
            source=process,
        )
    )
    sink.emit(
        RuntimeEvent.create(
            session_id="s1",
            event_type="session.finished",
            relation="FINISHED_SESSION",
            source=session,
        )
    )


def test_graph_deduplicates_nodes_and_aggregates_edges(tmp_path: Path) -> None:
    stream = tmp_path / "run.jsonl"
    _emit_complete_stream(stream)

    graph = build_execution_graph(stream)
    payload = graph.to_dict()

    assert payload["session_id"] == "s1"
    assert payload["event_count"] == 6
    assert payload["node_count"] == 4
    assert payload["edge_count"] == 3

    read_edge = next(edge for edge in payload["edges"] if edge["relation"] == "OPENED_READ")
    assert read_edge["source"] == "process:s1:10"
    assert read_edge["target"] == "file:/tmp/a.txt"
    assert read_edge["count"] == 2
    assert len(read_edge["event_ids"]) == 2
    assert read_edge["causal"] is True
    assert read_edge["backends"] == ["strace"]


def test_source_only_lifecycle_event_updates_node_without_fake_edge(tmp_path: Path) -> None:
    stream = tmp_path / "run.jsonl"
    _emit_complete_stream(stream)

    graph = build_execution_graph(stream)
    process = next(node for node in graph.to_dict()["nodes"] if node["id"] == "process:s1:10")
    assert "process.started" in process["event_types"]
    assert "process.exited" in process["event_types"]
    assert not any(edge.relation == "EXITED" for edge in graph.edges)


def test_graph_rejects_invalid_stream(tmp_path: Path) -> None:
    stream = tmp_path / "bad.jsonl"
    stream.write_text('{"not":"an execweave event"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid ExecWeave event stream"):
        build_execution_graph(stream)


def test_graph_writer_refuses_existing_nonempty_output_and_preserves_metadata(
    tmp_path: Path,
) -> None:
    stream = tmp_path / "run.jsonl"
    _emit_complete_stream(stream)
    graph = build_execution_graph(stream)
    output = tmp_path / "run.graph.json"
    metadata = {"correlation": {"skipped_ambiguous": 2}}

    written = write_execution_graph(graph, output, metadata=metadata)
    assert written == output.resolve()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["graph_schema_version"] == "0.1"
    assert payload["metadata"] == metadata

    with pytest.raises(FileExistsError):
        write_execution_graph(graph, output)
