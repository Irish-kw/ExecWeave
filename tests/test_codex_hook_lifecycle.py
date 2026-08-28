from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.codex_hook_cli import main as codex_hook_main
from execweave.codex_hook_lifecycle import (
    CODEX_HOOKS_REFERENCE,
    OFFICIAL_CODEX_HOOK_EVENTS,
    codex_official_hook_lifecycle_events,
)


def _base(event: str) -> dict:
    return {
        "session_id": "session-1",
        "transcript_path": "/tmp/unstable-rollout.jsonl",
        "cwd": "/repo",
        "hook_event_name": event,
        "model": "gpt-5.6-codex",
    }


def test_official_event_set_excludes_undocumented_interrupt() -> None:
    assert "Interrupt" not in OFFICIAL_CODEX_HOOK_EVENTS
    assert OFFICIAL_CODEX_HOOK_EVENTS == {
        "SessionStart",
        "SessionEnd",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PreCompact",
        "PostCompact",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "Stop",
    }


def test_session_start_and_end_are_first_class_without_transcript_claims() -> None:
    started = codex_official_hook_lifecycle_events(
        {
            **_base("SessionStart"),
            "source": "resume",
            "permission_mode": "default",
        },
        timestamp="2026-08-28T06:00:00Z",
    )
    ended = codex_official_hook_lifecycle_events(
        {**_base("SessionEnd"), "reason": "other"},
        timestamp="2026-08-28T06:05:00Z",
    )

    assert started[0]["relation"] == "STARTED_PROVIDER_SESSION"
    assert ended[0]["relation"] == "OBSERVED_PROVIDER_SESSION_END"
    assert started[0]["target"]["id"] == ended[0]["target"]["id"]
    assert started[0]["attributes"]["codex_session_source"] == "resume"
    assert ended[0]["attributes"]["codex_session_end_reason"] == "other"
    assert ended[0]["attributes"]["main_thread_only_by_contract"] is True
    for event in [*started, *ended]:
        assert event["attributes"]["official_hook_contract"] is True
        assert event["attributes"]["official_hook_reference"] == CODEX_HOOKS_REFERENCE
        assert "transcript_path" not in event["attributes"]


def test_permission_request_does_not_invent_tool_use_id() -> None:
    events = codex_official_hook_lifecycle_events(
        {
            **_base("PermissionRequest"),
            "turn_id": "turn-1",
            "permission_mode": "default",
            "tool_name": "Bash",
            "tool_input": {
                "command": "sudo apt update",
                "description": "needs escalation",
            },
        },
        timestamp="2026-08-28T06:01:00Z",
    )

    event = events[0]
    assert event["relation"] == "OBSERVED_PERMISSION_REQUEST"
    assert event["target"]["type"] == "permission_request"
    assert event["target"]["attributes"]["identity_semantics"] == (
        "provider_hook_observation_without_tool_use_id"
    )
    serialized = json.dumps(event)
    assert "tool_use_id" not in serialized
    assert "sudo apt update" not in serialized
    assert event["attributes"]["description_present"] is True


def test_compaction_observations_do_not_assert_pre_post_pairing() -> None:
    pre = codex_official_hook_lifecycle_events(
        {
            **_base("PreCompact"),
            "turn_id": "turn-2",
            "trigger": "auto",
        },
        timestamp="2026-08-28T06:02:00Z",
    )[0]
    post = codex_official_hook_lifecycle_events(
        {
            **_base("PostCompact"),
            "turn_id": "turn-2",
            "trigger": "auto",
        },
        timestamp="2026-08-28T06:02:01Z",
    )[0]

    assert pre["relation"] == "OBSERVED_PRE_COMPACTION"
    assert post["relation"] == "COMPACTED_CONTEXT"
    assert pre["target"]["id"] != post["target"]["id"]
    assert pre["attributes"]["pre_post_pairing_asserted"] is False
    assert post["attributes"]["pre_post_pairing_asserted"] is False
    assert pre["target"]["attributes"]["trigger"] == "auto"
    assert post["target"]["attributes"]["trigger"] == "auto"


def test_stop_is_observation_not_irreversible_completion() -> None:
    events = codex_official_hook_lifecycle_events(
        {
            **_base("Stop"),
            "turn_id": "turn-3",
            "permission_mode": "default",
            "stop_hook_active": False,
            "last_assistant_message": "final before any hook continuation",
        },
        timestamp="2026-08-28T06:03:00Z",
    )

    event = events[0]
    assert event["relation"] == "OBSERVED_TURN_STOP"
    assert "hook_may_request_continuation" in event["target"]["attributes"]["completion_semantics"]
    assert event["attributes"]["last_assistant_message_stored_separately"] is True
    assert "final before any hook continuation" not in json.dumps(event)


def test_cli_writes_official_lifecycle_and_full_fidelity_together(
    monkeypatch, tmp_path: Path
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {
        **_base("PostCompact"),
        "cwd": str(tmp_path),
        "turn_id": "turn-4",
        "trigger": "manual",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert codex_hook_main(["--sidecar", str(sidecar)]) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = [record["relation"] for record in records]
    assert "COMPACTED_CONTEXT" in relations
    assert "OBSERVED_PROVIDER_METADATA" in relations
    compact = next(record for record in records if record["relation"] == "COMPACTED_CONTEXT")
    assert compact["attributes"]["compaction_trigger"] == "manual"
