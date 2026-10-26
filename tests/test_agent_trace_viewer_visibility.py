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


def test_agent_viewer_supports_provider_capability_fallback_for_rollout_agents() -> None:
    root = {
        "id": "agent:Codex",
        "type": "agent",
        "name": "Codex",
        "attributes": {"provider": "codex"},
    }
    rollout_agent = {
        "id": "agent:codex:rollout:r1:thread:t1",
        "type": "agent",
        "name": "/root/worker",
        "attributes": {"provider": "codex", "thread_id": "t1"},
    }
    capability = {
        "id": "agent-trace-capability:codex",
        "type": "agent_trace_capability",
        "name": "Codex trace visibility",
        "attributes": {
            "provider": "codex",
            "agent_identity_visibility": "provider_exposed_thread_identity",
            "subagent_visibility": "provider_exposed_rollout_graph",
            "reasoning_visibility": "provider_exposed_plaintext_summary_or_encoded",
        },
    }
    child = {
        "id": "agent:codex:rollout:r1:thread:t2",
        "type": "agent",
        "name": "/root/worker/child",
        "attributes": {"provider": "codex", "thread_id": "t2"},
    }
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "rollout-visibility-test",
        "event_count": 2,
        "node_count": 4,
        "edge_count": 2,
        "nodes": [root, rollout_agent, capability, child],
        "edges": [
            _edge(root["id"], capability["id"], "DECLARES_AGENT_TRACE_VISIBILITY", 1),
            _edge(rollout_agent["id"], child["id"], "SPAWNED_AGENT", 2),
        ],
    }

    html = render_graph_html(graph)

    assert "SPAWNED_AGENT" in html
    assert "provider_exposed_rollout_graph" in html
    assert "provider_exposed_thread_identity" in html
    assert "provider_exposed_plaintext_summary_or_encoded" in html
    assert "Provider exposes rollout graph" not in html
