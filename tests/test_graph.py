import hashlib
import json
from pathlib import Path

import pytest

from execweave.graph import GraphAccumulator, build_execution_graph, write_execution_graph
from execweave.inference_gateway import litellm_response_to_events
from execweave.inference_identity import gateway_runtime_identity_event
from execweave.model_runtime import vllm_response_to_events
from execweave.schema import Entity, RuntimeEvent
from execweave.semantic import merge_semantic_sidecar
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


def test_incremental_graph_accumulator_matches_canonical_builder(tmp_path: Path) -> None:
    stream = tmp_path / "run.jsonl"
    _emit_complete_stream(stream)

    canonical = build_execution_graph(stream).to_dict()
    accumulator = GraphAccumulator(session_id="s1", source_path=stream)
    for line in stream.read_text(encoding="utf-8").splitlines():
        if line.strip():
            accumulator.apply(json.loads(line))
    incremental = accumulator.to_dict()

    canonical.pop("built_at")
    incremental.pop("built_at")
    assert incremental == canonical


def test_incremental_graph_can_drop_raw_edge_ids_but_keep_justification(tmp_path: Path) -> None:
    stream = tmp_path / "live.jsonl"
    accumulator = GraphAccumulator(
        session_id="s1",
        source_path=stream,
        retain_event_ids=False,
    )
    accumulator.apply(
        {
            "schema_version": "0.2",
            "event_id": "raw-event-id",
            "session_id": "s1",
            "timestamp": "2026-08-26T00:00:00Z",
            "sequence": 1,
            "event_type": "inference.identity",
            "relation": "SAME_INFERENCE_REQUEST",
            "source": {"id": "inference-request:gateway:g1", "type": "inference_request"},
            "target": {"id": "inference-request:runtime:r1", "type": "inference_request"},
            "attributes": {
                "causal": False,
                "inferred": False,
                "identity_exact": True,
                "identity_method": "shared_request_id",
                "shared_request_id_hash": "0123456789abcdef0123456789abcdef",
                "supporting_event_ids": ["support-a", "support-b"],
            },
        }
    )

    edge = accumulator.to_dict()["edges"][0]
    assert edge["event_ids"] == []
    assert edge["causal"] is False
    assert edge["inferred"] is False
    assert edge["identity_exact"] is True
    assert edge["identity_methods"] == ["shared_request_id"]
    assert edge["identity_hashes"] == ["0123456789abcdef0123456789abcdef"]
    assert edge["supporting_event_ids"] == ["support-a", "support-b"]


def test_source_only_lifecycle_event_updates_node_without_fake_edge(tmp_path: Path) -> None:
    stream = tmp_path / "run.jsonl"
    _emit_complete_stream(stream)

    graph = build_execution_graph(stream)
    process = next(node for node in graph.to_dict()["nodes"] if node["id"] == "process:s1:10")
    assert "process.started" in process["event_types"]
    assert "process.exited" in process["event_types"]
    assert not any(edge.relation == "EXITED" for edge in graph.edges)


def test_exact_inference_identity_survives_semantic_merge_and_graph_materialization(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime.jsonl"
    sidecar = tmp_path / "inference.jsonl"
    merged = tmp_path / "merged.jsonl"
    _emit_complete_stream(runtime)

    runtime_events = [
        json.loads(line) for line in runtime.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    timestamp = next(
        event["timestamp"] for event in runtime_events if event["event_type"] == "session.started"
    )
    shared = "PRIVATE_GRAPH_SHARED_REQUEST_ID"

    records = []
    records.extend(
        litellm_response_to_events(
            {
                "id": "gw-graph-1",
                "model": "proxy-alias-response",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
            requested_model="assistant",
            resolved_model="qwen/local",
            provider_name="vLLM",
            request_id="gw-graph-1",
            timestamp=timestamp,
        )
    )
    records.extend(
        vllm_response_to_events(
            {
                "id": "rt-graph-1",
                "model": "qwen/local",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
            request_id="rt-graph-1",
            timestamp=timestamp,
        )
    )
    records.append(
        gateway_runtime_identity_event(
            gateway="litellm",
            gateway_request_id="gw-graph-1",
            runtime="vllm",
            runtime_request_id="rt-graph-1",
            shared_request_id=shared,
            timestamp=timestamp,
        )
    )
    sidecar.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    merge_semantic_sidecar(runtime, sidecar, merged)
    graph_payload = build_execution_graph(merged).to_dict()
    rendered = json.dumps(graph_payload, sort_keys=True)

    assert shared not in merged.read_text(encoding="utf-8")
    assert shared not in rendered
    node_ids = {node["id"] for node in graph_payload["nodes"]}
    assert "inference-request:litellm:gw-graph-1" in node_ids
    assert "inference-request:vllm:rt-graph-1" in node_ids

    identity_edge = next(
        edge for edge in graph_payload["edges"] if edge["relation"] == "SAME_INFERENCE_REQUEST"
    )
    assert identity_edge["source"] == "inference-request:litellm:gw-graph-1"
    assert identity_edge["target"] == "inference-request:vllm:rt-graph-1"
    assert identity_edge["causal"] is False
    assert identity_edge["inferred"] is False
    assert identity_edge["identity_exact"] is True
    assert identity_edge["identity_methods"] == ["shared_request_id"]
    assert identity_edge["identity_hashes"] == [
        hashlib.sha256(shared.encode("utf-8")).hexdigest()[:32]
    ]


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
    assert payload["graph_schema_version"] == "0.2"
    assert payload["metadata"] == metadata

    with pytest.raises(FileExistsError):
        write_execution_graph(graph, output)
