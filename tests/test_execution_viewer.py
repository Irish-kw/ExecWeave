from __future__ import annotations

from execweave.viewer_projection import render_graph_html


def _edge(source: str, target: str, relation: str, sequence: int) -> dict:
    return {
        "id": f"{source}--{relation}-->{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"e-{sequence}"],
        "event_types": [f"semantic.test.{relation.lower()}"],
        "backends": ["semantic"],
        "attributions": ["provider_integration"],
        "causal": False,
    }


def _content(letter: str) -> dict:
    digest = letter * 64
    return {
        "id": f"observed-content:sha256:{digest}",
        "type": "observed_content",
        "name": "antigravity.execution_stop_error",
        "attributes": {
            "provider": "antigravity",
            "path": f"content/sha256/{digest}.txt",
            "sha256": digest,
            "size_bytes": 12,
            "media_type": "text/plain",
            "representation": "utf-8",
            "content_kind": "antigravity.execution_stop_error",
            "complete_from_source": True,
        },
    }


def test_execution_viewer_uses_only_exact_incident_error_payload_edges() -> None:
    agent = {
        "id": "agent:Antigravity",
        "type": "agent",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity"},
    }
    execution_two = {
        "id": "agent-execution:antigravity:conversation-stop:2",
        "type": "agent_execution",
        "name": "Antigravity execution 2",
        "attributes": {
            "provider": "antigravity",
            "execution_num": 2,
            "termination_reason": "error",
            "fully_idle": True,
        },
    }
    execution_three = {
        "id": "agent-execution:antigravity:conversation-stop:3",
        "type": "agent_execution",
        "name": "Antigravity execution 3",
        "attributes": {
            "provider": "antigravity",
            "execution_num": 3,
            "termination_reason": "model_stop",
            "fully_idle": True,
        },
    }
    content_two = _content("a")
    content_three = _content("b")
    edges = [
        _edge(agent["id"], execution_two["id"], "OBSERVED_EXECUTION_STOP", 1),
        _edge(agent["id"], execution_two["id"], "OBSERVED_EXECUTION_ERROR", 2),
        _edge(
            execution_two["id"],
            content_two["id"],
            "OBSERVED_EXECUTION_ERROR_CONTENT",
            3,
        ),
        _edge(agent["id"], execution_three["id"], "OBSERVED_EXECUTION_STOP", 4),
        _edge(
            execution_three["id"],
            content_three["id"],
            "OBSERVED_EXECUTION_ERROR_CONTENT",
            5,
        ),
    ]
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "execution-viewer-test",
        "event_count": len(edges),
        "node_count": 5,
        "edge_count": len(edges),
        "nodes": [agent, execution_two, execution_three, content_two, content_three],
        "edges": edges,
    }

    html = render_graph_html(graph)

    assert "Execution Evidence" in html
    assert "Stored error payload" in html
    assert "Execution stop is provider-observed execution-loop evidence" in html
    assert "agent_execution → observed_content" in html
    assert "no timing or execution-number join" in html
    assert "edge.target===value.id" in html
    assert "edge.source===value.id" in html
    assert "OBSERVED_EXECUTION_ERROR_CONTENT" in html
    assert execution_two["id"] in html
    assert execution_three["id"] in html
    assert content_two["attributes"]["path"] in html
    assert content_three["attributes"]["path"] in html
    assert "execweaveAppendContentInspector" in html
    assert "execweaveAppendDelegationInspector" in html
