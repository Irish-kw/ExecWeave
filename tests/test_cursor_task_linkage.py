from __future__ import annotations

from pathlib import Path

from execweave.content_store import FullFidelityContentStore
from execweave.cursor_delegation import cursor_delegation_events
from execweave.cursor_full_fidelity import cursor_hook_to_content_events


def _start(**extra: object) -> dict[str, object]:
    return {
        "hook_event_name": "subagentStart",
        "conversation_id": "parent-1",
        "parent_conversation_id": "parent-1",
        "generation_id": "generation-1",
        "session_id": "session-1",
        "subagent_id": "child-1",
        "subagent_type": "research",
        "tool_call_id": "tc-1",
        "task": "inspect auth flow",
        **extra,
    }


def _trigger(events: list[dict]) -> dict | None:
    return next(
        (
            event
            for event in events
            if event.get("relation") == "REQUESTED_SUBTASK"
            and event.get("source", {}).get("type") == "tool_call"
        ),
        None,
    )


def test_cursor_subagent_start_links_exact_triggering_task_call(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    events = cursor_delegation_events(
        _start(),
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    trigger = _trigger(events)
    assert trigger is not None
    assert trigger["source"]["id"] == "tool-call:cursor:parent-1:tc-1"
    assert trigger["target"]["id"] == "subtask:cursor:parent-1:subagent:child-1"
    assert trigger["attributes"]["provider_tool_call_id_exact"] is True
    assert trigger["attributes"]["provider_parent_conversation_id_exact"] is True
    assert trigger["attributes"]["provider_subagent_id_exact"] is True
    assert trigger["attributes"]["trigger_basis"] == "subagentStart.tool_call_id"
    assert trigger["attributes"]["causal"] is False

    tool_events = cursor_hook_to_content_events(
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "parent-1",
            "generation_id": "generation-1",
            "session_id": "session-1",
            "tool_name": "Task",
            "tool_use_id": "tc-1",
            "tool_input": {"task": "inspect auth flow"},
        },
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    observed_input = next(
        event for event in tool_events if event["relation"] == "OBSERVED_TOOL_INPUT"
    )
    assert observed_input["source"]["id"] == trigger["source"]["id"]


def test_cursor_trigger_link_refuses_parent_conversation_mismatch(tmp_path: Path) -> None:
    events = cursor_delegation_events(
        _start(parent_conversation_id="other-parent"),
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    assert _trigger(events) is None
    assert any(
        event["relation"] == "REQUESTED_SUBTASK"
        and event["source"]["id"] == "agent:Cursor"
        for event in events
    )


def test_cursor_trigger_link_requires_provider_tool_call_id(tmp_path: Path) -> None:
    payload = _start()
    payload.pop("tool_call_id")
    events = cursor_delegation_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    assert _trigger(events) is None
    assert any(event["relation"] == "ASSIGNED_AGENT_TASK" for event in events)
