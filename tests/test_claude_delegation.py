from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.claude_delegation import claude_delegation_events
from execweave.claude_full_fidelity import claude_hook_to_content_events
from execweave.claude_hook_cli import main as claude_hook_main
from execweave.content_store import FullFidelityContentStore


def _payload(event: str) -> dict[str, object]:
    return {
        "session_id": "claude-session-1",
        "cwd": "/repo",
        "permission_mode": "default",
        "hook_event_name": event,
    }


def test_subagent_stop_normalizes_exact_return_and_reuses_result_content(tmp_path: Path) -> None:
    payload = {
        **_payload("SubagentStop"),
        "agent_id": "agent-7",
        "agent_type": "Explore",
        "last_assistant_message": "child final result",
    }
    content_events = claude_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T06:00:00Z",
    )

    events = claude_delegation_events(
        payload,
        content_events=content_events,
        timestamp="2026-08-28T06:00:00Z",
    )

    assert [event["relation"] for event in events] == [
        "RETURNED_AGENT_RESULT",
        "HAS_AGENT_RESULT_PAYLOAD",
    ]
    child_id = "agent:claude:claude-session-1:subagent:agent-7"
    assert events[0]["source"]["id"] == child_id
    assert events[0]["target"]["id"] == "agent:Claude Code"
    assert events[0]["attributes"]["provider_agent_id_exact"] is True
    assert events[0]["attributes"]["subtask_prompt_linkage_asserted"] is False

    produced = next(
        event for event in content_events if event["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    payload_event = events[1]
    assert payload_event["source"]["id"] == child_id
    assert payload_event["target"] == produced["target"]
    assert payload_event["attributes"]["content_sha256"] == produced["attributes"]["content_sha256"]
    assert payload_event["attributes"]["normalized_from_relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    assert "child final result" not in json.dumps(events)


def test_subagent_return_normalizer_requires_exact_agent_id(tmp_path: Path) -> None:
    payload = {
        **_payload("SubagentStop"),
        "last_assistant_message": "unlinked result",
    }
    content_events = claude_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T06:00:00Z",
    )

    assert claude_delegation_events(
        payload,
        content_events=content_events,
        timestamp="2026-08-28T06:00:00Z",
    ) == []


def test_subagent_start_does_not_invent_prompt_to_child_delegation() -> None:
    payload = {
        **_payload("SubagentStart"),
        "agent_id": "agent-7",
        "agent_type": "Explore",
        "prompt": "do not infer a task join from this field",
    }

    assert claude_delegation_events(
        payload,
        content_events=[],
        timestamp="2026-08-28T06:00:00Z",
    ) == []


def test_claude_hook_cli_emits_normalized_return_and_result_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    payload = {
        **_payload("SubagentStop"),
        "cwd": str(tmp_path),
        "agent_id": "agent-9",
        "agent_type": "Explore",
        "last_assistant_message": "stored child result",
    }
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert claude_hook_main(["--sidecar", str(sidecar)]) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = [record["relation"] for record in records]
    assert "RETURNED_TO" in relations
    assert "PRODUCED_ASSISTANT_RESPONSE" in relations
    assert "RETURNED_AGENT_RESULT" in relations
    assert "HAS_AGENT_RESULT_PAYLOAD" in relations

    produced = next(record for record in records if record["relation"] == "PRODUCED_ASSISTANT_RESPONSE")
    normalized = next(record for record in records if record["relation"] == "HAS_AGENT_RESULT_PAYLOAD")
    assert normalized["target"]["id"] == produced["target"]["id"]
    assert normalized["source"]["id"] == "agent:claude:claude-session-1:subagent:agent-9"
