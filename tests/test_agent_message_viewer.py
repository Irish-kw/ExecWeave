from __future__ import annotations

from execweave.viewer_projection import render_graph_html


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    sequence: int,
) -> dict[str, object]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"event-{sequence}"],
        "event_types": [f"semantic.codex.{relation.lower()}"],
        "backends": ["semantic"],
        "attributions": ["codex_rollout_trace"],
        "causal": False,
    }


def test_agent_message_viewer_shows_send_delivery_context_and_consumption_evidence() -> None:
    digest = "c" * 64
    root = {
        "id": "agent:codex:root",
        "type": "agent",
        "name": "/root",
        "attributes": {"provider": "codex", "thread_id": "root-thread"},
    }
    child = {
        "id": "agent:codex:child",
        "type": "agent",
        "name": "/root/agent_b",
        "attributes": {"provider": "codex", "thread_id": "child-thread"},
    }
    message = {
        "id": "agent-message:codex:m1",
        "type": "agent_message",
        "name": "Codex agent message",
        "attributes": {
            "provider": "codex",
            "author": "/root",
            "recipient": "/root/agent_b",
            "conversation_item_id": "m1",
        },
    }
    inference = {
        "id": "inference-call:codex:inf-child",
        "type": "inference_call",
        "name": "gpt-5.6-codex",
        "attributes": {
            "provider": "codex",
            "thread_id": "child-thread",
            "inference_call_id": "inf-child",
        },
    }
    payload = {
        "id": f"observed-content:codex.agent_message.payload:sha256:{digest}",
        "type": "observed_content",
        "name": "codex.agent_message.payload",
        "attributes": {
            "sha256": digest,
            "path": f"content/sha256/{digest}.json",
            "media_type": "application/json",
            "size_bytes": 148,
            "content_kind": "codex.agent_message.payload",
            "representation": "parsed_json_canonical",
            "complete_from_source": True,
        },
    }
    edges = [
        _edge("send", root["id"], message["id"], "SENT_AGENT_MESSAGE", 1),
        _edge("deliver", message["id"], child["id"], "DELIVERED_AGENT_MESSAGE", 2),
        _edge(
            "context",
            message["id"],
            inference["id"],
            "INCLUDED_AGENT_MESSAGE_IN_INFERENCE",
            3,
        ),
        _edge("consume", child["id"], message["id"], "CONSUMED_AGENT_MESSAGE", 4),
        _edge("payload", message["id"], payload["id"], "HAS_AGENT_MESSAGE_PAYLOAD", 5),
    ]
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "message-evidence-viewer",
        "event_count": len(edges),
        "node_count": 5,
        "edge_count": len(edges),
        "nodes": [root, child, message, inference, payload],
        "edges": edges,
    }

    html = render_graph_html(graph)

    assert "Message Evidence" in html
    assert "message-stage-grid" in html
    assert "execweaveAppendMessageInspector" in html
    assert "SENT_AGENT_MESSAGE" in html
    assert "DELIVERED_AGENT_MESSAGE" in html
    assert "INCLUDED_AGENT_MESSAGE_IN_INFERENCE" in html
    assert "CONSUMED_AGENT_MESSAGE" in html
    assert "Inspect inference" in html
    assert "not proof that the model attended to" in html
    assert "No evidence” is not a failure state" in html
    assert "Agent Message Payload" in html
    assert f"content/sha256/{digest}.json" in html


def test_agent_message_viewer_keeps_missing_stages_neutral() -> None:
    message = {
        "id": "agent-message:codex:m2",
        "type": "agent_message",
        "name": "Codex agent message",
        "attributes": {"provider": "codex"},
    }
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "message-evidence-neutral",
        "event_count": 0,
        "node_count": 1,
        "edge_count": 0,
        "nodes": [message],
        "edges": [],
    }

    html = render_graph_html(graph)

    assert "value.textContent=observed?'Observed':'No evidence'" in html
    assert "No evidence” is not a failure state" in html
    assert "message-stage is-failed" not in html
