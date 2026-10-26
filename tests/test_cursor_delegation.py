from __future__ import annotations

from pathlib import Path

from execweave.content_store import FullFidelityContentStore
from execweave.cursor_delegation import cursor_delegation_events
from execweave.provider_lifecycle import provider_lifecycle_annotation


def _payload(event: str, **extra: object) -> dict[str, object]:
    return {
        "hook_event_name": event,
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "generation_id": "generation-1",
        "subagent_id": "sub-7",
        "subagent_type": "research",
        **extra,
    }


def _read_content(root: Path, event: dict) -> str:
    path = root / event["target"]["attributes"]["path"]
    return path.read_text(encoding="utf-8")


def test_cursor_subagent_start_becomes_exact_delegation_with_full_prompt(tmp_path: Path) -> None:
    events = cursor_delegation_events(
        _payload(
            "subagentStart",
            task="trace every authentication call",
            description="inspect auth flow",
        ),
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )

    requested = next(event for event in events if event["relation"] == "REQUESTED_SUBTASK")
    assigned = next(event for event in events if event["relation"] == "ASSIGNED_AGENT_TASK")
    prompt = next(event for event in events if event["relation"] == "HAS_SUBTASK_PROMPT")
    description = next(
        event for event in events if event["relation"] == "HAS_SUBTASK_DESCRIPTION"
    )

    assert requested["source"]["id"] == "agent:Cursor"
    assert requested["target"]["id"] == "subtask:cursor:conversation-1:subagent:sub-7"
    assert requested["attributes"]["exact_child_agent_linkage"] is True
    assert assigned["source"]["id"] == requested["target"]["id"]
    assert assigned["target"]["id"] == "agent:cursor:conversation-1:subagent:sub-7"
    assert assigned["attributes"]["provider_subagent_id_exact"] is True
    assert _read_content(tmp_path, prompt) == "trace every authentication call"
    assert _read_content(tmp_path, description) == "inspect auth flow"

    lifecycle = provider_lifecycle_annotation(assigned)
    assert lifecycle is not None
    assert lifecycle.kind == "subagent"
    assert lifecycle.stage == "task_assigned"


def test_cursor_subagent_stop_records_exact_return_and_result_payload(tmp_path: Path) -> None:
    events = cursor_delegation_events(
        _payload("subagentStop", summary="found three auth call sites"),
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:01Z",
    )

    returned = next(event for event in events if event["relation"] == "RETURNED_AGENT_RESULT")
    result = next(event for event in events if event["relation"] == "HAS_AGENT_RESULT_PAYLOAD")

    assert returned["source"]["id"] == "agent:cursor:conversation-1:subagent:sub-7"
    assert returned["target"]["id"] == "agent:Cursor"
    assert returned["attributes"]["exact_child_agent_linkage"] is True
    assert _read_content(tmp_path, result) == "found three auth call sites"

    lifecycle = provider_lifecycle_annotation(returned)
    assert lifecycle is not None
    assert lifecycle.kind == "subagent"
    assert lifecycle.stage == "result_returned"


def test_cursor_delegation_refuses_to_invent_child_without_provider_id(tmp_path: Path) -> None:
    payload = _payload("subagentStart", task="do work")
    payload.pop("subagent_id")

    events = cursor_delegation_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )

    assert events == []
