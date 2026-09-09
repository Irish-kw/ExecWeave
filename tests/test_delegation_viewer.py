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
        "event_types": [f"semantic.test.{relation.lower()}"],
        "backends": ["semantic"],
        "attributions": ["provider_integration"],
        "causal": False,
    }


def _content(
    content_kind: str,
    digest: str,
    *,
    size_bytes: int = 64,
) -> dict[str, object]:
    return {
        "id": f"observed-content:{content_kind}:sha256:{digest}",
        "type": "observed_content",
        "name": content_kind,
        "attributes": {
            "sha256": digest,
            "path": f"content/sha256/{digest}.txt",
            "media_type": "text/plain; charset=utf-8",
            "size_bytes": size_bytes,
            "content_kind": content_kind,
            "representation": "raw_utf8",
            "complete_from_source": True,
        },
    }


def test_cursor_subtask_viewer_marks_exact_child_linkage_and_payloads() -> None:
    root = {
        "id": "agent:Cursor",
        "type": "agent",
        "name": "Cursor",
        "attributes": {"provider": "cursor"},
    }
    subtask = {
        "id": "subtask:cursor:session-1:subagent:child-1",
        "type": "subtask",
        "name": "Inspect parser",
        "attributes": {
            "provider": "cursor",
            "subagent_id": "child-1",
            "exact_child_agent_linkage": True,
        },
    }
    child = {
        "id": "agent:cursor:subagent:child-1",
        "type": "agent",
        "name": "Cursor subagent child-1",
        "attributes": {
            "provider": "cursor",
            "subagent_id": "child-1",
            "identity_semantics": "provider_subagent_id",
        },
    }
    prompt = _content("cursor.subtask_prompt", "a" * 64)
    description = _content("cursor.subtask_description", "b" * 64)
    edges = [
        _edge("request", root["id"], subtask["id"], "REQUESTED_SUBTASK", 1),
        _edge("assign", subtask["id"], child["id"], "ASSIGNED_AGENT_TASK", 2),
        _edge("prompt", subtask["id"], prompt["id"], "HAS_SUBTASK_PROMPT", 3),
        _edge(
            "description",
            subtask["id"],
            description["id"],
            "HAS_SUBTASK_DESCRIPTION",
            4,
        ),
    ]
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "cursor-delegation-viewer",
        "event_count": len(edges),
        "node_count": 5,
        "edge_count": len(edges),
        "nodes": [root, subtask, child, prompt, description],
        "edges": edges,
    }

    html = render_graph_html(graph)

    assert "REQUESTED_SUBTASK" in html
    assert "ASSIGNED_AGENT_TASK" in html
    assert "HAS_SUBTASK_PROMPT" in html
    assert "HAS_SUBTASK_DESCRIPTION" in html
    assert '"exact_child_agent_linkage":true' in html
    assert f"content/sha256/{'a' * 64}.txt" in html
    assert f"content/sha256/{'b' * 64}.txt" in html
    assert "Delegation Evidence" not in html


def test_opencode_subtask_viewer_does_not_invent_child_session_join() -> None:
    requester = {
        "id": "agent:opencode:session:parent",
        "type": "agent",
        "name": "OpenCode parent session",
        "attributes": {"provider": "opencode", "session_id": "parent"},
    }
    subtask = {
        "id": "subtask:opencode:parent:m1:p1",
        "type": "subtask",
        "name": "Review tests",
        "attributes": {
            "provider": "opencode",
            "session_id": "parent",
            "message_id": "m1",
            "part_id": "p1",
        },
    }
    profile = {
        "id": "agent-profile:opencode:reviewer",
        "type": "agent_profile",
        "name": "reviewer",
        "attributes": {"provider": "opencode", "native_agent_name": "reviewer"},
    }
    separate_child = {
        "id": "agent:opencode:session:child",
        "type": "agent",
        "name": "OpenCode child session",
        "attributes": {"provider": "opencode", "session_id": "child"},
    }
    prompt = _content("opencode.subtask_prompt", "c" * 64)
    edges = [
        _edge("request", requester["id"], subtask["id"], "REQUESTED_SUBTASK", 1),
        _edge("target", subtask["id"], profile["id"], "TARGETS_AGENT_PROFILE", 2),
        _edge("prompt", subtask["id"], prompt["id"], "HAS_SUBTASK_PROMPT", 3),
        _edge(
            "child-session",
            requester["id"],
            separate_child["id"],
            "HAS_CHILD_AGENT_SESSION",
            4,
        ),
    ]
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "opencode-delegation-viewer",
        "event_count": len(edges),
        "node_count": 5,
        "edge_count": len(edges),
        "nodes": [requester, subtask, profile, separate_child, prompt],
        "edges": edges,
    }

    html = render_graph_html(graph)

    assert "REQUESTED_SUBTASK" in html
    assert "TARGETS_AGENT_PROFILE" in html
    assert "HAS_SUBTASK_PROMPT" in html
    assert "HAS_CHILD_AGENT_SESSION" in html
    assert "ASSIGNED_AGENT_TASK" not in html
    assert "Delegation Evidence" not in html


def test_payload_helper_links_direct_observed_content_peer() -> None:
    content = _content("cursor.agent_result", "d" * 64)
    agent = {
        "id": "agent:cursor:subagent:child-1",
        "type": "agent",
        "name": "Cursor subagent child-1",
        "attributes": {"provider": "cursor"},
    }
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "direct-content-peer",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [agent, content],
        "edges": [
            _edge(
                "result-payload",
                agent["id"],
                content["id"],
                "HAS_AGENT_RESULT_PAYLOAD",
                1,
            )
        ],
    }

    html = render_graph_html(graph)

    assert "HAS_AGENT_RESULT_PAYLOAD" in html
    assert "cursor.agent_result" in html
    assert f"content/sha256/{'d' * 64}.txt" in html
    assert "window.__execweaveStaticGraph=" in html
    assert "execweaveAppendPayloadLinks" not in html
