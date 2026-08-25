from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.cli import main
from execweave.graph import build_execution_graph
from execweave.schema import SCHEMA_VERSION
from execweave.semantic import merge_semantic_sidecar
from execweave.validate import validate_event_stream


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _runtime_events() -> list[dict]:
    agent = {"type": "agent", "id": "agent:Claude Code", "name": "Claude Code", "attributes": {}}
    session = {"type": "session", "id": "session:s1", "name": "s1", "attributes": {}}
    process = {
        "type": "process",
        "id": "process:123:1770000000000000",
        "name": "bash",
        "attributes": {"pid": 123, "ppid": 1, "create_time": 1770000000.0},
    }
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-start",
            "session_id": "s1",
            "timestamp": "2026-08-25T00:00:00Z",
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": agent,
            "target": session,
            "sequence": 1,
            "attributes": {"backend": "portable"},
        },
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-process",
            "session_id": "s1",
            "timestamp": "2026-08-25T00:00:01Z",
            "event_type": "process.started",
            "relation": "LAUNCHED",
            "source": session,
            "target": process,
            "sequence": 2,
            "attributes": {"backend": "portable", "attribution": "polling", "causal": True},
        },
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": "runtime-finish",
            "session_id": "s1",
            "timestamp": "2026-08-25T00:00:10Z",
            "event_type": "session.finished",
            "relation": "FINISHED_SESSION",
            "source": session,
            "target": None,
            "sequence": 3,
            "attributes": {"backend": "portable", "return_code": 0},
        },
    ]


def _semantic_events() -> list[dict]:
    return [
        {
            "timestamp": "2026-08-25T00:00:02Z",
            "event_type": "semantic.tool.called",
            "relation": "CALLED_TOOL",
            "source": {
                "type": "agent",
                "id": "agent:Claude Code",
                "name": "Claude Code",
                "attributes": {},
            },
            "target": {
                "type": "tool",
                "id": "tool:claude-code:Bash",
                "name": "Bash",
                "attributes": {"provider": "claude-code"},
            },
            "attributes": {"causal": True, "attribution": "claude_hook"},
        },
        {
            "timestamp": "2026-08-25T00:00:03Z",
            "event_type": "semantic.tool.process",
            "relation": "SPAWNED_PROCESS",
            "source": {
                "type": "tool",
                "id": "tool:claude-code:Bash",
                "name": "Bash",
                "attributes": {},
            },
            "target": {
                "type": "process_reference",
                "id": "process-pid:123",
                "name": "123",
                "attributes": {"pid": 123},
            },
            "attributes": {"causal": True, "attribution": "claude_hook"},
        },
        {
            "timestamp": "2026-08-25T00:00:04Z",
            "event_type": "semantic.mcp.called",
            "relation": "CALLED_MCP",
            "source": {
                "type": "agent",
                "id": "agent:Claude Code",
                "name": "Claude Code",
                "attributes": {},
            },
            "target": {
                "type": "mcp_server",
                "id": "mcp:github",
                "name": "GitHub MCP",
                "attributes": {},
            },
            "attributes": {"causal": True, "attribution": "claude_hook"},
        },
    ]


def test_semantic_merge_validates_and_materializes_agent_tool_process_graph(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    merged = tmp_path / "merged.jsonl"
    _write_jsonl(runtime, _runtime_events())
    _write_jsonl(semantic, _semantic_events())
    original_runtime = runtime.read_text(encoding="utf-8")

    result = merge_semantic_sidecar(runtime, semantic, merged)

    assert result.runtime_event_count == 3
    assert result.semantic_event_count == 3
    assert result.merged_event_count == 6
    assert result.resolved_process_references == 1
    assert result.unresolved_process_references == 0
    assert runtime.read_text(encoding="utf-8") == original_runtime

    validation = validate_event_stream(merged)
    assert validation.valid, validation.errors
    events = [json.loads(line) for line in merged.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == list(range(1, 7))
    assert events[0]["event_type"] == "session.started"
    assert events[-1]["event_type"] == "session.finished"

    process_link = next(event for event in events if event["event_type"] == "semantic.tool.process")
    assert process_link["target"]["type"] == "process"
    assert process_link["target"]["id"] == "process:123:1770000000000000"
    assert process_link["attributes"]["backend"] == "semantic"
    assert process_link["attributes"]["resolved_process_references"] == {
        "process-pid:123": "process:123:1770000000000000"
    }

    graph = build_execution_graph(merged).to_dict()
    node_types = {node["type"] for node in graph["nodes"]}
    assert {"agent", "tool", "mcp_server", "process"}.issubset(node_types)
    relations = {edge["relation"] for edge in graph["edges"]}
    assert {"CALLED_TOOL", "SPAWNED_PROCESS", "CALLED_MCP"}.issubset(relations)


def test_semantic_merge_keeps_unresolved_process_reference(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    merged = tmp_path / "merged.jsonl"
    _write_jsonl(runtime, _runtime_events())
    records = _semantic_events()[:1]
    records.append(
        {
            "timestamp": "2026-08-25T00:00:05Z",
            "event_type": "semantic.tool.process",
            "relation": "SPAWNED_PROCESS",
            "source": {
                "type": "tool",
                "id": "tool:claude-code:Bash",
                "name": "Bash",
                "attributes": {},
            },
            "target": {
                "type": "process_reference",
                "id": "process-pid:999",
                "name": "999",
                "attributes": {"pid": 999},
            },
            "attributes": {"causal": False, "attribution": "timestamp_hint"},
        }
    )
    _write_jsonl(semantic, records)

    result = merge_semantic_sidecar(runtime, semantic, merged)
    assert result.resolved_process_references == 0
    assert result.unresolved_process_references == 1
    events = [json.loads(line) for line in merged.read_text(encoding="utf-8").splitlines()]
    link = next(event for event in events if event["event_type"] == "semantic.tool.process")
    assert link["target"]["type"] == "process_reference"
    assert link["target"]["attributes"]["unresolved"] is True


def test_semantic_merge_rejects_events_outside_runtime_interval(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    merged = tmp_path / "merged.jsonl"
    _write_jsonl(runtime, _runtime_events())
    record = _semantic_events()[0]
    record["timestamp"] = "2026-08-25T00:00:11Z"
    _write_jsonl(semantic, [record])

    with pytest.raises(ValueError, match="outside the runtime session interval"):
        merge_semantic_sidecar(runtime, semantic, merged)
    assert not merged.exists()


def test_semantic_merge_cli_writes_valid_stream(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    merged = tmp_path / "merged.jsonl"
    _write_jsonl(runtime, _runtime_events())
    _write_jsonl(semantic, _semantic_events())

    result = main(
        [
            "semantic-merge",
            str(runtime),
            str(semantic),
            "--output",
            str(merged),
        ]
    )

    assert result == 0
    assert validate_event_stream(merged).valid
