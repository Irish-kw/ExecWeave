from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from execweave.live import _LiveState
from execweave.viewer_external_endpoints import EXTERNAL_NODE_ID
from execweave.viewer_projection import project_viewer_graph, render_graph_html


ALL_PROVIDERS = (
    "claude",
    "codex",
    "antigravity",
    "cursor",
    "opencode",
    "ollama",
    "llamacpp",
    "vllm",
    "lmstudio",
    "anthropic",
    "openrouter",
    "litellm",
    "openai-compatible",
)

NATIVE_SUBAGENT_PROVIDERS = {
    "claude",
    "codex",
    "antigravity",
    "cursor",
    "opencode",
}


def _selected_providers() -> tuple[str, ...]:
    selected = os.environ.get("EXECWEAVE_PROVIDER_MATRIX", "").strip().lower()
    if selected == "agy":
        selected = "antigravity"
    return (selected,) if selected in ALL_PROVIDERS else ALL_PROVIDERS


def _content_node(provider: str, *, digest: str) -> dict[str, object]:
    content_kind = f"{provider}.assistant_response"
    return {
        "id": f"observed-content:{content_kind}:sha256:{digest}",
        "type": "observed_content",
        "name": content_kind,
        "attributes": {
            "sha256": digest,
            "path": f"content/sha256/{digest}.txt",
            "media_type": "text/plain; charset=utf-8",
            "size_bytes": 17,
            "content_kind": content_kind,
            "representation": "raw_utf8",
            "complete_from_source": True,
        },
    }


def _dashboard_graph(provider: str) -> dict[str, object]:
    agent_id = f"agent:{provider}:root"
    tool_id = f"tool:{provider}:apply_patch"
    file_id = f"file:/workspace/{provider}-notes.md"
    content = _content_node(provider, digest=hashlib.sha256(provider.encode()).hexdigest())
    nodes: list[dict[str, object]] = [
        {
            "id": agent_id,
            "type": "agent",
            "name": provider,
            "attributes": {"provider": provider},
        },
        {
            "id": tool_id,
            "type": "tool",
            "name": "apply_patch",
            "attributes": {"provider": provider, "tool_name": "apply_patch"},
        },
        {
            "id": file_id,
            "type": "file",
            "name": f"{provider}-notes.md",
            "attributes": {"path": f"/workspace/{provider}-notes.md"},
        },
        {
            "id": "endpoint:203.0.113.10:443",
            "type": "network_endpoint",
            "name": "203.0.113.10:443",
            "event_types": ["network.connection"],
        },
        content,
    ]
    edges = [
        {
            "id": "agent-tool",
            "source": agent_id,
            "target": tool_id,
            "relation": "USES_TOOL",
            "count": 1,
        },
        {
            "id": "tool-file",
            "source": tool_id,
            "target": file_id,
            "relation": "DECLARED_TARGET",
            "count": 1,
            "event_types": ["semantic.tool.target_declared"],
        },
        {
            "id": "agent-content",
            "source": agent_id,
            "target": content["id"],
            "relation": "OBSERVED_CONVERSATION_CONTENT",
            "count": 1,
            "event_types": ["semantic.conversation.content.observed"],
        },
        {
            "id": "agent-external",
            "source": agent_id,
            "target": "endpoint:203.0.113.10:443",
            "relation": "CONNECTED_TO",
            "count": 1,
            "event_types": ["network.connection"],
        },
    ]
    return {
        "graph_schema_version": "0.2",
        "session_id": f"dashboard-{provider}",
        "event_count": len(edges),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


@pytest.mark.parametrize("provider", _selected_providers())
def test_every_provider_keeps_dashboard_graph_raw_events_and_file_targets(
    provider: str,
) -> None:
    graph = _dashboard_graph(provider)
    projected = project_viewer_graph(graph)
    node_ids = {node["id"] for node in projected["nodes"]}
    edge_pairs = {
        (edge["source"], edge["relation"], edge["target"])
        for edge in projected["edges"]
    }

    assert f"agent:{provider}:root" in node_ids
    assert f"file:/workspace/{provider}-notes.md" in node_ids
    assert (
        f"tool:{provider}:apply_patch",
        "DECLARED_TARGET",
        f"file:/workspace/{provider}-notes.md",
    ) in edge_pairs
    assert EXTERNAL_NODE_ID in node_ids

    html = render_graph_html(graph)
    assert "window.__execweaveStaticGraph=" in html
    assert "window.__execweaveStaticConversations=" in html
    assert 'data-log-mode="raw"' in html
    assert 'id="raw-rows"' in html
    assert f"{provider}-notes.md" in html


@pytest.mark.parametrize("provider", _selected_providers())
def test_every_provider_collapses_repeated_result_and_operation_nodes(
    provider: str,
) -> None:
    graph = _dashboard_graph(provider)
    agent_id = f"agent:{provider}:root"
    tool_id = f"tool:{provider}:apply_patch"
    for index in (1, 2):
        graph["nodes"].extend(
            [
                {
                    "id": f"tool-result:{provider}:{index}",
                    "type": "tool_result",
                    "name": "apply_patch result",
                    "first_seen": f"2026-09-03T00:00:0{index}Z",
                    "last_seen": f"2026-09-03T00:00:0{index}Z",
                    "event_count": 1,
                    "attributes": {"provider": provider},
                },
                {
                    "id": f"agent-operation:{provider}:{index}",
                    "type": "agent_operation",
                    "name": "manage_subagents list",
                    "first_seen": f"2026-09-03T00:00:0{index}Z",
                    "last_seen": f"2026-09-03T00:00:0{index}Z",
                    "event_count": 1,
                    "attributes": {"provider": provider},
                },
            ]
        )
        graph["edges"].extend(
            [
                {
                    "id": f"result-{index}",
                    "source": tool_id,
                    "target": f"tool-result:{provider}:{index}",
                    "relation": "TOOL_RESULT_RETURNED",
                    "count": 1,
                },
                {
                    "id": f"operation-{index}",
                    "source": agent_id,
                    "target": f"agent-operation:{provider}:{index}",
                    "relation": "OBSERVED_AGENT_OPERATION",
                    "count": 1,
                },
            ]
        )

    projected = project_viewer_graph(graph)
    result_nodes = [
        node for node in projected["nodes"] if node.get("type") == "tool_result"
    ]
    operation_nodes = [
        node for node in projected["nodes"] if node.get("type") == "agent_operation"
    ]
    assert len(result_nodes) == 1
    assert len(operation_nodes) == 1
    assert result_nodes[0]["attributes"]["viewer_occurrence_count"] == 2
    assert operation_nodes[0]["attributes"]["viewer_occurrence_count"] == 2
    result_edge = next(
        edge
        for edge in projected["edges"]
        if edge.get("relation") == "TOOL_RESULT_RETURNED"
    )
    operation_edge = next(
        edge
        for edge in projected["edges"]
        if edge.get("relation") == "OBSERVED_AGENT_OPERATION"
    )
    assert result_edge["count"] == 2
    assert operation_edge["count"] == 2


def _runtime_event(
    provider: str,
    event_id: str,
    sequence: int,
    event_type: str,
    relation: str,
    target: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.2",
        "event_id": event_id,
        "session_id": f"raw-{provider}",
        "timestamp": f"2026-09-03T00:00:0{sequence}Z",
        "sequence": sequence,
        "event_type": event_type,
        "relation": relation,
        "source": {
            "id": f"process:{provider}",
            "type": "process",
            "name": provider,
            "attributes": {"provider": provider},
        },
        "target": target,
        "attributes": {"backend": "portable", "provider": provider},
    }


@pytest.mark.parametrize("provider", _selected_providers())
def test_every_provider_raw_log_retains_process_file_and_network_events(
    provider: str,
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events.jsonl"
    events = [
        _runtime_event(
            provider,
            f"{provider}-process",
            1,
            "process.started",
            "LAUNCHED",
            {"id": f"process:{provider}:child", "type": "process", "name": "agent"},
        ),
        _runtime_event(
            provider,
            f"{provider}-file",
            2,
            "filesystem.created",
            "CREATED",
            {
                "id": f"file:/workspace/{provider}-notes.md",
                "type": "file",
                "name": f"{provider}-notes.md",
                "attributes": {"path": f"/workspace/{provider}-notes.md"},
            },
        ),
        _runtime_event(
            provider,
            f"{provider}-network",
            3,
            "network.connection",
            "CONNECTED_TO",
            {
                "id": f"endpoint:203.0.113.{10 + (len(provider) % 10)}:443",
                "type": "network_endpoint",
                "name": f"203.0.113.{10 + (len(provider) % 10)}:443",
            },
        ),
    ]
    event_path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )

    payload = _LiveState(f"raw-{provider}", event_path).live_update(-1)
    raw_events = payload["raw_events"]
    assert [entry["event"]["event_type"] for entry in raw_events] == [
        "process.started",
        "filesystem.created",
        "network.connection",
    ]
    assert f"{provider}-notes.md" in json.dumps(raw_events, ensure_ascii=False)
    graph = payload["graph"]
    assert any(
        node.get("type") == "file" and node.get("name") == f"{provider}-notes.md"
        for node in graph["nodes"]
    )


@pytest.mark.parametrize("provider", _selected_providers())
def test_every_provider_raw_log_includes_semantic_only_file_targets(
    provider: str,
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events.jsonl"
    semantic_path = tmp_path / "semantic.jsonl"
    started = _runtime_event(
        provider,
        f"{provider}-session-start",
        1,
        "session.started",
        "STARTED_SESSION",
        {"id": f"session:raw-{provider}", "type": "session", "name": provider},
    )
    event_path.write_text(json.dumps(started) + "\n", encoding="utf-8")
    semantic_event = {
        "timestamp": "2026-09-03T00:00:02Z",
        "event_type": f"semantic.{provider}.file.declared",
        "relation": "DECLARED_TARGET",
        "source": {
            "id": f"tool-call:{provider}:write-1",
            "type": "tool_call",
            "name": "write",
            "attributes": {"provider": provider, "tool_call_id": "write-1"},
        },
        "target": {
            "id": f"file:/workspace/{provider}-semantic-only.md",
            "type": "file",
            "name": f"{provider}-semantic-only.md",
            "attributes": {"path": f"/workspace/{provider}-semantic-only.md"},
        },
        "attributes": {"backend": "semantic", "provider": provider},
    }
    semantic_path.write_text(
        json.dumps(semantic_event) + "\n" + json.dumps(semantic_event) + "\n",
        encoding="utf-8",
    )

    payload = _LiveState(
        f"raw-{provider}",
        event_path,
        semantic_path,
    ).live_update(-1)
    semantic_rows = [
        entry for entry in payload["raw_events"] if entry.get("stream") == "semantic.jsonl"
    ]
    assert len(semantic_rows) == 1
    assert semantic_rows[0]["evidence_event_count"] == 2
    assert semantic_rows[0]["event"]["relation"] == "DECLARED_TARGET"
    assert f"{provider}-semantic-only.md" in json.dumps(semantic_rows, ensure_ascii=False)
    assert any(
        node.get("name") == f"{provider}-semantic-only.md"
        for node in payload["graph"]["nodes"]
    )


def test_provider_matrix_distinguishes_native_subagents_from_root_only_runtimes() -> None:
    assert NATIVE_SUBAGENT_PROVIDERS <= set(ALL_PROVIDERS)
    root_only = set(ALL_PROVIDERS) - NATIVE_SUBAGENT_PROVIDERS
    assert root_only == {
        "ollama",
        "llamacpp",
        "vllm",
        "lmstudio",
        "anthropic",
        "openrouter",
        "litellm",
        "openai-compatible",
    }
