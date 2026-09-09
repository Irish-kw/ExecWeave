from __future__ import annotations

from pathlib import Path

from execweave.content_store import FullFidelityContentStore
from execweave.cursor_delegation import cursor_delegation_events
from execweave.graph import GraphAccumulator
from execweave.opencode_task_linkage import opencode_task_session_events


def _materialized_edge(events: list[dict], relation: str) -> dict:
    accumulator = GraphAccumulator(
        session_id="delegation-identity",
        source_path=Path("delegation-identity.jsonl"),
    )
    for event in events:
        accumulator.apply(event)
    return next(edge for edge in accumulator.to_dict()["edges"] if edge["relation"] == relation)


def test_cursor_exact_child_identity_survives_graph_materialization(tmp_path: Path) -> None:
    events = cursor_delegation_events(
        {
            "hook_event_name": "subagentStart",
            "conversation_id": "conversation-1",
            "session_id": "session-1",
            "generation_id": "generation-1",
            "subagent_id": "sub-7",
            "subagent_type": "research",
            "task": "inspect authentication",
        },
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-09-09T07:00:00Z",
    )

    assigned = _materialized_edge(events, "ASSIGNED_AGENT_TASK")
    assert assigned["identity_exact"] is True
    assert assigned["identity_methods"] == ["cursor_provider_subagent_id"]


def test_opencode_exact_task_session_identity_survives_graph_materialization() -> None:
    events = opencode_task_session_events(
        {
            "hook_event_name": "event",
            "event_type": "message.part.updated",
            "sessionID": "parent",
            "event": {
                "type": "message.part.updated",
                "properties": {
                    "part": {
                        "id": "part-task",
                        "sessionID": "parent",
                        "messageID": "message-task",
                        "type": "tool",
                        "callID": "call-task",
                        "tool": "task",
                        "state": {
                            "status": "running",
                            "input": {
                                "prompt": "inspect authentication",
                                "description": "inspect auth",
                                "subagent_type": "explore",
                                "background": False,
                            },
                            "metadata": {
                                "parentSessionId": "parent",
                                "sessionId": "child",
                            },
                        },
                    }
                },
            },
        },
        timestamp="2026-09-09T07:00:00Z",
    )

    assigned = _materialized_edge(events, "ASSIGNED_AGENT_TASK")
    assert assigned["identity_exact"] is True
    assert assigned["identity_methods"] == [
        "opencode_task_tool_parent_and_child_session_ids"
    ]
