from __future__ import annotations

from pathlib import Path

from execweave.cursor_hook_cli import _default_sidecar, cursor_hook_config
from execweave.cursor_hook_contract import (
    OFFICIAL_CURSOR_HOOK_EVENTS,
    cursor_official_hook_semantic_events,
)


def _base(event: str) -> dict:
    return {
        "conversation_id": "conversation-1",
        "generation_id": "generation-1",
        "session_id": "session-1",
        "hook_event_name": event,
        "cursor_version": "3.13.25",
        "workspace_roots": ["/repo"],
        "model": "composer",
        "model_id": "composer-2",
    }


def test_official_event_set_includes_app_lifecycle_surface() -> None:
    assert len(OFFICIAL_CURSOR_HOOK_EVENTS) == 21
    assert "workspaceOpen" in OFFICIAL_CURSOR_HOOK_EVENTS
    assert set(cursor_hook_config()["hooks"]) == set(OFFICIAL_CURSOR_HOOK_EVENTS)


def test_session_start_and_end_share_exact_provider_session_identity() -> None:
    started = cursor_official_hook_semantic_events(
        {
            **_base("sessionStart"),
            "is_background_agent": False,
            "composer_mode": "agent",
        },
        timestamp="2026-08-28T07:20:00Z",
    )[0]
    ended = cursor_official_hook_semantic_events(
        {
            **_base("sessionEnd"),
            "reason": "completed",
            "duration_ms": 45000,
            "is_background_agent": False,
            "final_status": "completed",
        },
        timestamp="2026-08-28T07:21:00Z",
    )[0]

    assert started["relation"] == "STARTED_PROVIDER_SESSION"
    assert ended["relation"] == "OBSERVED_PROVIDER_SESSION_END"
    assert started["target"]["id"] == "provider-session:cursor:session-1"
    assert ended["target"]["id"] == started["target"]["id"]
    assert started["attributes"]["session_creation_blocked_by_hook_asserted"] is False
    assert ended["attributes"]["flow_control_ignored_by_provider"] is True


def test_precompact_is_observation_not_completion() -> None:
    event = cursor_official_hook_semantic_events(
        {
            **_base("preCompact"),
            "trigger": "auto",
            "context_usage_percent": 85,
            "context_tokens": 120000,
            "context_window_size": 128000,
            "message_count": 45,
            "messages_to_compact": 30,
            "is_first_compaction": True,
        },
        timestamp="2026-08-28T07:22:00Z",
    )[0]

    assert event["relation"] == "OBSERVED_PRE_COMPACTION"
    assert event["attributes"]["compaction_completion_asserted"] is False
    assert event["attributes"]["compaction_block_or_modify_supported"] is False
    assert event["target"]["type"] == "context_compaction"


def test_stop_does_not_claim_provider_session_ended() -> None:
    event = cursor_official_hook_semantic_events(
        {
            **_base("stop"),
            "status": "completed",
            "loop_count": 2,
        },
        timestamp="2026-08-28T07:23:00Z",
    )[0]

    assert event["relation"] == "OBSERVED_TURN_STOP"
    assert event["attributes"]["agent_loop_can_resume_via_followup"] is True
    assert event["attributes"]["provider_session_end_asserted"] is False
    assert event["target"]["attributes"]["completion_semantics"] == (
        "agent_loop_ended_before_optional_hook_followup"
    )


def test_workspace_open_has_no_fake_conversation_or_session_identity(
    tmp_path: Path,
) -> None:
    payload = {
        "hook_event_name": "workspaceOpen",
        "cursor_version": "3.13.25",
        "workspace_roots": [str(tmp_path), str(tmp_path / "second")],
        "user_email": "local@example.com",
    }
    events = cursor_official_hook_semantic_events(
        payload,
        timestamp="2026-08-28T07:24:00Z",
    )

    opened = next(event for event in events if event["relation"] == "OBSERVED_WORKSPACE_OPEN")
    roots = [event for event in events if event["relation"] == "WORKSPACE_HAS_ROOT"]
    assert opened["source"]["type"] == "provider_application"
    assert opened["target"]["type"] == "workspace"
    assert opened["attributes"]["conversation_identity_available"] is False
    assert opened["attributes"]["session_identity_available"] is False
    assert len(roots) == 2
    assert {event["target"]["name"] for event in roots} == {
        str(tmp_path),
        str(tmp_path / "second"),
    }

    sidecar = _default_sidecar(payload)
    assert sidecar.parent == tmp_path / ".execweave" / "semantic" / "cursor"
    assert sidecar.name.startswith("workspace-")
    assert sidecar.name.endswith(".jsonl")
