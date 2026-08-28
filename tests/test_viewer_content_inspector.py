from __future__ import annotations

from copy import deepcopy

import pytest

from execweave.viewer_content_inspector import (
    decorate_viewer_content_references,
    viewer_content_reference,
)
from execweave.viewer_projection import project_viewer_graph, render_graph_html


def _content_node(
    content_kind: str,
    *,
    digest: str = "a" * 64,
    suffix: str = "json",
) -> dict[str, object]:
    return {
        "id": f"observed-content:{content_kind}:sha256:{digest}",
        "type": "observed_content",
        "name": content_kind,
        "attributes": {
            "sha256": digest,
            "path": f"content/sha256/{digest}.{suffix}",
            "media_type": "application/json" if suffix == "json" else "text/plain; charset=utf-8",
            "size_bytes": 1234,
            "content_kind": content_kind,
            "representation": "parsed_json_canonical" if suffix == "json" else "raw_utf8",
            "complete_from_source": True,
        },
        "event_count": 1,
        "event_types": ["semantic.content.observed"],
    }


def _graph(node: dict[str, object]) -> dict[str, object]:
    return {
        "graph_schema_version": "0.2",
        "session_id": "content-viewer-test",
        "event_count": 1,
        "node_count": 1,
        "edge_count": 0,
        "nodes": [node],
        "edges": [],
    }


@pytest.mark.parametrize(
    ("content_kind", "category"),
    [
        ("claude.user_prompt", "Prompt"),
        ("codex.tool_input", "Tool Input"),
        ("opencode.tool_output", "Tool Output"),
        ("inference_gateway.openrouter.response", "Response"),
        ("litellm.provider_metadata", "Provider Metadata"),
        ("codex.agent_message.payload", "Agent Message Payload"),
        ("codex.reasoning.text", "Reasoning Text"),
        ("codex.reasoning.summary", "Reasoning Summary"),
        ("codex.reasoning.encoded", "Encoded Reasoning"),
        ("codex.rollout.raw_payload.inference_request", "Inference Request"),
        ("codex.rollout.raw_payload.inference_response", "Inference Response"),
        ("codex.terminal.request", "Terminal Request"),
        ("codex.terminal.result", "Terminal Result"),
        ("codex.code_cell.source_js", "Code Cell Source"),
        ("codex.rollout.raw_payload.protocol_event", "Raw Provider Payload"),
    ],
)
def test_content_reference_categories_are_cross_provider(
    content_kind: str,
    category: str,
) -> None:
    reference = viewer_content_reference(_content_node(content_kind))
    assert reference is not None
    assert reference["category"] == category
    assert reference["viewer_only"] is True
    assert reference["content_embedded_in_viewer"] is False


def test_content_reference_rejects_arbitrary_or_hash_mismatched_paths() -> None:
    traversal = _content_node("claude.tool_input")
    traversal["attributes"]["path"] = "../semantic.jsonl"
    assert viewer_content_reference(traversal) is None

    mismatch = _content_node("claude.tool_input")
    mismatch["attributes"]["path"] = f"content/sha256/{'b' * 64}.json"
    assert viewer_content_reference(mismatch) is None

    absolute = _content_node("claude.tool_input")
    absolute["attributes"]["path"] = f"/tmp/content/sha256/{'a' * 64}.json"
    assert viewer_content_reference(absolute) is None


def test_projection_decorates_reference_without_mutating_or_embedding_raw_graph() -> None:
    raw = _graph(_content_node("cursor.tool_input"))
    before = deepcopy(raw)

    projected = decorate_viewer_content_references(raw)

    assert raw == before
    marker = projected["viewer_content_projection"]
    assert marker == {
        "schema_version": "0.1",
        "viewer_only": True,
        "reference_count": 1,
        "content_embedded_in_viewer": False,
        "http_content_serving_enabled": False,
    }
    node = projected["nodes"][0]
    assert node["name"] == "Tool Input"
    reference = node["attributes"]["viewer_content"]
    assert reference["safe_relative_path"].startswith("content/sha256/")
    assert reference["complete_from_source"] is True


def test_projected_standalone_viewer_has_expandable_reference_only_inspector() -> None:
    raw = _graph(_content_node("claude.tool_input"))

    html = render_graph_html(raw)

    assert "content-inspector" in html
    assert "Tool Input" in html
    assert f"content/sha256/{'a' * 64}.json" in html
    assert "Open stored content" in html
    assert "sandbox" in html
    assert "location.protocol==='file:'" in html
    assert "Content bytes are not fetched over HTTP by this inspector" in html
    assert "This does not imply visibility into hidden model/provider state" in html
    assert "content_embedded_in_viewer\":false" in html
    assert "http_content_serving_enabled\":false" in html
    assert "PRIVATE_TOOL_BODY_THAT_IS_NOT_IN_THE_GRAPH" not in html


def test_standalone_viewer_exposes_agent_communication_and_activity_inspector() -> None:
    payload = _content_node("codex.agent_message.payload", digest="b" * 64)
    agent = {
        "id": "agent:codex:root",
        "type": "agent",
        "name": "/root",
        "attributes": {"provider": "codex", "thread_id": "root"},
    }
    message = {
        "id": "agent-message:codex:m1",
        "type": "agent_message",
        "name": "Codex agent message",
        "attributes": {"author": "/root", "recipient": "/root/agent_b"},
    }
    raw = {
        "graph_schema_version": "0.2",
        "session_id": "agent-viewer-test",
        "event_count": 2,
        "node_count": 3,
        "edge_count": 2,
        "nodes": [agent, message, payload],
        "edges": [
            {
                "id": "send",
                "source": agent["id"],
                "target": message["id"],
                "relation": "SENT_AGENT_MESSAGE",
                "count": 1,
                "first_sequence": 1,
                "last_sequence": 1,
                "event_ids": ["e1"],
                "event_types": ["semantic.codex.rollout.agent_message.sent"],
                "backends": ["semantic"],
                "attributions": ["codex_rollout_trace"],
                "causal": False,
            },
            {
                "id": "payload",
                "source": message["id"],
                "target": payload["id"],
                "relation": "HAS_AGENT_MESSAGE_PAYLOAD",
                "count": 1,
                "first_sequence": 2,
                "last_sequence": 2,
                "event_ids": ["e2"],
                "event_types": ["semantic.codex.rollout.content.observed"],
                "backends": ["semantic"],
                "attributions": ["codex_rollout_trace"],
                "causal": False,
            },
        ],
    }

    html = render_graph_html(raw)

    assert "Agent communications" in html
    assert "Agent activity" in html
    assert "Inspect edge" in html
    assert "Inspect peer" in html
    assert "SENT_AGENT_MESSAGE" in html
    assert "Agent Message Payload" in html
    assert f"content/sha256/{'b' * 64}.json" in html
    assert "execweavePayloadNodes" in html


def test_invalid_content_ref_stays_generic_and_does_not_gain_local_file_link() -> None:
    node = _content_node("claude.tool_input")
    node["attributes"]["path"] = "../../etc/passwd"
    raw = _graph(node)

    projected = project_viewer_graph(raw)

    assert "viewer_content_projection" not in projected
    assert "viewer_content" not in projected["nodes"][0]["attributes"]
    assert projected["nodes"][0]["name"] == "claude.tool_input"


def test_content_projection_coexists_with_loopback_endpoint_collapse() -> None:
    content = _content_node("opencode.tool_output")
    process = {"id": "process:p1", "type": "process", "name": "ollama"}
    nodes: list[dict[str, object]] = [content, process]
    edges: list[dict[str, object]] = []
    for index in range(4):
        address = f"127.0.0.1:{50000 + index}"
        endpoint_id = f"endpoint:{address}"
        nodes.append({"id": endpoint_id, "type": "network_endpoint", "name": address})
        edges.append(
            {
                "id": f"process:p1--CONNECTED_TO-->{endpoint_id}",
                "source": "process:p1",
                "target": endpoint_id,
                "relation": "CONNECTED_TO",
                "count": 1,
                "first_sequence": index + 1,
                "last_sequence": index + 1,
                "event_ids": [f"e-{index}"],
                "event_types": ["network.connection"],
                "backends": ["portable"],
                "attributions": ["process_polling"],
                "causal": True,
            }
        )
    raw = {
        "graph_schema_version": "0.2",
        "session_id": "combined-projection",
        "event_count": len(edges) + 1,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }

    projected = project_viewer_graph(raw)

    assert projected["viewer_content_projection"]["reference_count"] == 1
    assert projected["viewer_projection"]["cluster_count"] == 1
    observed = next(node for node in projected["nodes"] if node["type"] == "observed_content")
    assert observed["name"] == "Tool Output"
    assert observed["attributes"]["viewer_content"]["viewer_only"] is True
