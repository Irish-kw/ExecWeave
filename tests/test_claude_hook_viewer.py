from __future__ import annotations

import pytest

from execweave.viewer_content_inspector import viewer_content_reference
from execweave.viewer_projection import render_graph_html


@pytest.mark.parametrize(
    ("content_kind", "category"),
    [
        ("claude.prompt_expansion.original_prompt", "Prompt Expansion"),
        ("claude.permission.tool_input", "Permission Evidence"),
        ("claude.permission_denied.reason", "Permission Evidence"),
        ("claude.task.subject", "Agent Task"),
        ("claude.task.description", "Agent Task"),
        ("claude.compaction.custom_instructions", "Context Compaction"),
        ("claude.compaction.summary", "Context Compaction"),
        ("claude.elicitation.requested_schema", "MCP Elicitation"),
        ("claude.elicitation.result_content", "MCP Elicitation"),
        ("claude.notification.message", "Provider Notification"),
        ("claude.stop.background_tasks", "Agent Runtime State"),
        ("claude.stop.session_crons", "Agent Runtime State"),
    ],
)
def test_claude_official_hook_content_has_specific_viewer_category(
    content_kind: str,
    category: str,
) -> None:
    digest = "a" * 64
    node = {
        "type": "observed_content",
        "id": f"observed-content:{content_kind}",
        "attributes": {
            "path": f"content/sha256/{digest}.txt",
            "sha256": digest,
            "content_kind": content_kind,
            "size_bytes": 12,
            "media_type": "text/plain",
            "representation": "text",
            "complete_from_source": True,
        },
    }

    reference = viewer_content_reference(node)

    assert reference is not None
    assert reference["category"] == category
    assert reference["content_embedded_in_viewer"] is False


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
        "event_types": [f"semantic.claude.{relation.lower()}"],
        "backends": ["semantic"],
        "attributions": ["claude_official_hook_contract"],
        "causal": False,
    }


def test_agent_viewer_includes_claude_task_lifecycle_in_communications() -> None:
    agent = {
        "id": "agent:Claude Code",
        "type": "agent",
        "name": "Claude Code",
        "attributes": {"provider": "claude"},
    }
    task = {
        "id": "agent-task:claude:session-1:task-7",
        "type": "agent_task",
        "name": "Inspect auth path",
        "attributes": {"provider": "claude", "task_id": "task-7"},
    }
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "claude-task-viewer",
        "event_count": 2,
        "node_count": 2,
        "edge_count": 2,
        "nodes": [agent, task],
        "edges": [
            _edge(agent["id"], task["id"], "CREATED_AGENT_TASK", 1),
            _edge(agent["id"], task["id"], "COMPLETED_AGENT_TASK", 2),
        ],
    }

    html = render_graph_html(graph)

    assert "CREATED_AGENT_TASK" in html
    assert "COMPLETED_AGENT_TASK" in html
    assert "agent_task" in html
    assert "Agent communications" in html
