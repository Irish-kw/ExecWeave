from __future__ import annotations

import json
from pathlib import Path

from execweave.graph import GraphAccumulator, build_execution_graph
from execweave.provider_lifecycle import provider_lifecycle_annotation
from execweave.schema import Entity, RuntimeEvent
from execweave.semantic import merge_semantic_sidecar
from execweave.sink import JsonlSink


def _entity(kind: str, ident: str, *, name: str | None = None, **attributes: object) -> dict:
    return {
        "type": kind,
        "id": ident,
        "name": name,
        "attributes": dict(attributes),
    }


def _semantic_event(
    provider: str,
    relation: str,
    *,
    source: dict,
    target: dict,
    timestamp: str = "2026-08-27T00:00:00Z",
    **attributes: object,
) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": f"semantic.{provider}.focused",
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": provider,
            "causal": False,
            "inferred": False,
            **attributes,
        },
    }


def _annotation(event: dict) -> dict[str, str]:
    value = provider_lifecycle_annotation(event)
    assert value is not None
    return value.to_dict()


def test_provider_lifecycle_preserves_provider_specific_evidence_semantics() -> None:
    claude = _semantic_event(
        "claude",
        "TOOL_CALL_SUCCEEDED",
        source=_entity("tool_call", "tool-call:claude:s:c", tool_name="Read"),
        target=_entity("tool", "tool:claude:Read"),
    )
    codex = _semantic_event(
        "codex",
        "TOOL_CALL_RETURNED",
        source=_entity("tool_call", "tool-call:codex:s:c", tool_name="Bash"),
        target=_entity("tool", "tool:codex:Bash"),
    )
    gemini = _semantic_event(
        "gemini",
        "TOOL_RESULT_REPORTED_ERROR",
        source=_entity("tool", "tool:gemini:read_file"),
        target=_entity("tool_result", "tool-result:gemini:s:r"),
    )
    cursor = _semantic_event(
        "cursor",
        "DECLARED_TARGET",
        source=_entity("tool_call", "tool-call:cursor:s:c", tool_name="Read"),
        target=_entity("file", "file:/tmp/read.txt"),
    )
    opencode = _semantic_event(
        "opencode",
        "DECLARED_TARGET",
        source=_entity("tool_call", "tool-call:opencode:s:c", tool_name="write"),
        target=_entity("file", "file:/tmp/write.txt"),
    )

    assert _annotation(claude)["stage"] == "succeeded"
    assert _annotation(codex)["stage"] == "returned"
    assert _annotation(gemini)["stage"] == "provider_reported_error"
    assert _annotation(cursor) == {
        "schema_version": "0.1",
        "provider": "cursor",
        "kind": "file",
        "stage": "declared_read",
        "evidence_semantics": "classification_only",
    }
    assert _annotation(opencode)["stage"] == "declared_write"


def test_assistant_display_and_thought_do_not_claim_hidden_reasoning() -> None:
    display = _semantic_event(
        "claude",
        "DISPLAYED_ASSISTANT_TEXT",
        source=_entity("agent", "agent:Claude Code"),
        target=_entity("observed_content", "observed-content:text:1"),
        final=True,
    )
    thought = _semantic_event(
        "cursor",
        "OBSERVED_AGENT_THOUGHT",
        source=_entity("agent", "agent:Cursor"),
        target=_entity("observed_content", "observed-content:thought:1"),
        provider_labels_as_thinking_text=True,
    )

    assert _annotation(display)["stage"] == "final_display"
    thought_annotation = _annotation(thought)
    assert thought_annotation["kind"] == "assistant_thought"
    assert thought_annotation["stage"] == "provider_labeled_observed"
    assert thought_annotation["evidence_semantics"] == "classification_only"


def test_non_provider_os_edge_is_unchanged() -> None:
    accumulator = GraphAccumulator(session_id="s1", source_path="events.jsonl")
    accumulator.apply(
        {
            "schema_version": "0.2",
            "event_id": "e1",
            "session_id": "s1",
            "timestamp": "2026-08-27T00:00:00Z",
            "sequence": 1,
            "event_type": "filesystem.open",
            "relation": "OPENED_READ",
            "source": _entity("process", "process:s1:1"),
            "target": _entity("file", "file:/tmp/a"),
            "attributes": {"backend": "strace", "attribution": "syscall", "causal": True},
        }
    )

    edge = accumulator.to_dict()["edges"][0]
    assert edge["relation"] == "OPENED_READ"
    assert edge["causal"] is True
    assert "provider_lifecycle" not in edge


def _write_complete_runtime(path: Path) -> str:
    sink = JsonlSink(path)
    agent = Entity(type="agent", id="agent:test", name="test")
    session = Entity(type="session", id="session:s1", name="s1")
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
            event_type="session.finished",
            relation="FINISHED_SESSION",
            source=session,
        )
    )
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return records[0]["timestamp"]


def test_live_and_final_graph_materialize_same_provider_lifecycle(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    merged = tmp_path / "merged.jsonl"
    timestamp = _write_complete_runtime(runtime)

    semantic = [
        _semantic_event(
            "claude",
            "REQUESTED_TOOL_CALL",
            timestamp=timestamp,
            source=_entity("agent", "agent:Claude Code"),
            target=_entity("tool_call", "tool-call:claude:s:c", tool_name="Read"),
        ),
        _semantic_event(
            "codex",
            "TOOL_CALL_RETURNED",
            timestamp=timestamp,
            source=_entity("tool_call", "tool-call:codex:s:c", tool_name="Bash"),
            target=_entity("tool", "tool:codex:Bash"),
        ),
        _semantic_event(
            "gemini",
            "TOOL_RESULT_REPORTED_ERROR",
            timestamp=timestamp,
            source=_entity("tool", "tool:gemini:read_file"),
            target=_entity("tool_result", "tool-result:gemini:s:r"),
        ),
        _semantic_event(
            "cursor",
            "DECLARED_TARGET",
            timestamp=timestamp,
            source=_entity("tool_call", "tool-call:cursor:s:c", tool_name="Read"),
            target=_entity("file", "file:/tmp/cursor-read.txt"),
        ),
        _semantic_event(
            "opencode",
            "PRODUCED_ASSISTANT_TEXT",
            timestamp=timestamp,
            source=_entity("agent", "agent:OpenCode"),
            target=_entity("observed_content", "observed-content:opencode:text"),
        ),
    ]
    sidecar.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in semantic),
        encoding="utf-8",
    )
    merge_semantic_sidecar(runtime, sidecar, merged)

    final_graph = build_execution_graph(merged).to_dict()
    accumulator = GraphAccumulator(session_id="s1", source_path=merged)
    for line in merged.read_text(encoding="utf-8").splitlines():
        if line.strip():
            accumulator.apply(json.loads(line))
    live_graph = accumulator.to_dict()

    def lifecycle_by_edge(graph: dict) -> dict[str, object]:
        return {
            edge["id"]: edge.get("provider_lifecycle")
            for edge in graph["edges"]
            if "provider_lifecycle" in edge
        }

    expected = lifecycle_by_edge(final_graph)
    assert lifecycle_by_edge(live_graph) == expected
    assert len(expected) == 5
    assert {
        lifecycle[0]["provider"]
        for lifecycle in expected.values()
        if isinstance(lifecycle, list) and lifecycle
    } == {"claude", "codex", "gemini", "cursor", "opencode"}
