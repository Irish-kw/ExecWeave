from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.claude_hook_cli import claude_hook_config, main as claude_hook_main
from execweave.claude_hook_contract import (
    CLAUDE_HOOKS_REFERENCE,
    OFFICIAL_CLAUDE_HOOK_EVENTS,
    PASSIVE_CLAUDE_HOOK_EVENTS,
    UNSAFE_DEFAULT_CLAUDE_HOOK_EVENTS,
    claude_official_full_fidelity_events,
    claude_official_hook_semantic_events,
)
from execweave.content_store import FullFidelityContentStore


def _base(event: str) -> dict:
    return {
        "session_id": "session-1",
        "cwd": "/repo",
        "permission_mode": "default",
        "hook_event_name": event,
    }


def _load(tmp_path: Path, event: dict) -> bytes:
    return (tmp_path / event["attributes"]["content_path"]).read_bytes()


def test_current_official_event_set_and_passive_exclusions_are_explicit() -> None:
    assert len(OFFICIAL_CLAUDE_HOOK_EVENTS) == 31
    assert {
        "MessageDisplay",
        "InstructionsLoaded",
        "UserPromptExpansion",
        "PermissionDenied",
        "TaskCreated",
        "TaskCompleted",
        "DirectoryAdded",
        "PostCompact",
        "Elicitation",
        "ElicitationResult",
    }.issubset(OFFICIAL_CLAUDE_HOOK_EVENTS)
    assert UNSAFE_DEFAULT_CLAUDE_HOOK_EVENTS == {"WorktreeCreate", "FileChanged"}
    assert PASSIVE_CLAUDE_HOOK_EVENTS == (
        OFFICIAL_CLAUDE_HOOK_EVENTS - {"WorktreeCreate", "FileChanged"}
    )


def test_config_is_passive_and_keeps_official_message_display() -> None:
    hooks = claude_hook_config("execweave-claude-hook")["hooks"]

    assert set(hooks) == set(PASSIVE_CLAUDE_HOOK_EVENTS)
    assert "MessageDisplay" in hooks
    assert "WorktreeCreate" not in hooks
    assert "FileChanged" not in hooks
    assert hooks["PermissionRequest"][0]["matcher"] == "*"
    assert hooks["PermissionDenied"][0]["matcher"] == "*"
    assert "matcher" not in hooks["DirectoryAdded"][0]


def test_session_and_instructions_are_provider_grounded() -> None:
    started = claude_official_hook_semantic_events(
        {**_base("SessionStart"), "source": "resume"},
        timestamp="2026-08-28T06:30:00Z",
    )[0]
    loaded = claude_official_hook_semantic_events(
        {
            **_base("InstructionsLoaded"),
            "file_path": "/repo/CLAUDE.md",
            "memory_type": "Project",
            "load_reason": "session_start",
        },
        timestamp="2026-08-28T06:30:01Z",
    )[0]

    assert started["relation"] == "STARTED_PROVIDER_SESSION"
    assert started["target"]["id"] == "provider-session:claude:session-1"
    assert loaded["relation"] == "LOADED_INSTRUCTION_FILE"
    assert loaded["target"]["id"] == "file:/repo/CLAUDE.md"
    assert loaded["attributes"]["memory_type"] == "Project"
    assert loaded["attributes"]["load_reason"] == "session_start"
    assert loaded["attributes"]["official_hook_reference"] == CLAUDE_HOOKS_REFERENCE


def test_message_display_stays_with_existing_projector_not_duplicate_semantics() -> None:
    assert claude_official_hook_semantic_events(
        {
            **_base("MessageDisplay"),
            "turn_id": "turn-1",
            "message_id": "display-message-id",
            "index": 0,
            "final": True,
            "delta": "hello",
        },
        timestamp="2026-08-28T06:30:02Z",
    ) == []


def test_permission_request_has_no_fake_tool_id_but_denial_uses_exact_id() -> None:
    requested = claude_official_hook_semantic_events(
        {
            **_base("PermissionRequest"),
            "tool_name": "Bash",
            "tool_input": {"command": "sudo apt update"},
        },
        timestamp="2026-08-28T06:31:00Z",
    )[0]
    denied = claude_official_hook_semantic_events(
        {
            **_base("PermissionDenied"),
            "tool_name": "Bash",
            "tool_use_id": "toolu-denied",
            "tool_input": {"command": "rm -rf /tmp/build"},
            "reason": "Blocked by classifier",
        },
        timestamp="2026-08-28T06:31:01Z",
    )[0]

    assert requested["relation"] == "OBSERVED_PERMISSION_REQUEST"
    assert "tool_use_id" not in requested["target"]["attributes"]
    assert requested["target"]["attributes"]["identity_semantics"] == (
        "provider_hook_observation_without_tool_use_id"
    )
    assert denied["relation"] == "PERMISSION_DENIED_TOOL_CALL"
    assert denied["target"]["id"] == "tool-call:claude:session-1:toolu-denied"
    assert "rm -rf /tmp/build" not in json.dumps(denied)
    assert "Blocked by classifier" not in json.dumps(denied)


def test_tasks_use_provider_task_id_without_promoting_teammate_name_to_agent_id() -> None:
    created = claude_official_hook_semantic_events(
        {
            **_base("TaskCreated"),
            "task_id": "task-001",
            "task_subject": "Implement authentication",
            "task_description": "Add endpoints",
            "teammate_name": "implementer",
            "team_name": "session-a1b2",
        },
        timestamp="2026-08-28T06:32:00Z",
    )[0]
    idle = claude_official_hook_semantic_events(
        {
            **_base("TeammateIdle"),
            "teammate_name": "implementer",
            "team_name": "session-a1b2",
        },
        timestamp="2026-08-28T06:32:01Z",
    )[0]

    assert created["relation"] == "CREATED_AGENT_TASK"
    assert created["target"]["id"] == "agent-task:claude:session-1:task-001"
    assert created["target"]["attributes"]["teammate_name"] == "implementer"
    assert created["target"]["attributes"]["teammate_name_is_stable_agent_identity"] is False
    assert created["target"]["attributes"]["team_name_deprecated_by_provider"] is True
    assert idle["relation"] == "OBSERVED_TEAMMATE_IDLE"
    assert idle["target"]["type"] == "teammate_state"
    assert idle["target"]["attributes"]["teammate_name_is_stable_agent_identity"] is False


def test_directory_and_worktree_observations_use_exact_provider_paths() -> None:
    added = claude_official_hook_semantic_events(
        {
            **_base("DirectoryAdded"),
            "directory": "/repo/other",
            "source": "slash_command",
        },
        timestamp="2026-08-28T06:33:00Z",
    )[0]
    removed = claude_official_hook_semantic_events(
        {**_base("WorktreeRemove"), "worktree_path": "/repo/.claude/worktrees/feature"},
        timestamp="2026-08-28T06:33:01Z",
    )[0]

    assert added["relation"] == "ADDED_WORKING_DIRECTORY"
    assert added["target"]["name"] == "/repo/other"
    assert added["attributes"]["directory_add_source"] == "slash_command"
    assert removed["relation"] == "REMOVED_WORKTREE"
    assert removed["target"]["name"] == "/repo/.claude/worktrees/feature"


def test_filechanged_is_projectable_but_not_enabled_by_default() -> None:
    event = claude_official_hook_semantic_events(
        {
            **_base("FileChanged"),
            "file_path": "/repo/.env",
            "event": "change",
        },
        timestamp="2026-08-28T06:33:02Z",
    )[0]
    assert event["relation"] == "OBSERVED_FILE_CHANGE"
    assert event["attributes"]["default_execweave_hook_enabled"] is False
    assert "FileChanged" not in claude_hook_config()["hooks"]


def test_worktree_create_is_not_projected_or_default_enabled() -> None:
    payload = {**_base("WorktreeCreate"), "name": "feature-auth"}
    assert claude_official_hook_semantic_events(
        payload, timestamp="2026-08-28T06:33:03Z"
    ) == []
    assert "WorktreeCreate" not in claude_hook_config()["hooks"]


def test_compaction_summary_and_instructions_are_full_fidelity_without_inline_copy(
    tmp_path: Path,
) -> None:
    store = FullFidelityContentStore(tmp_path)
    pre = claude_official_full_fidelity_events(
        {
            **_base("PreCompact"),
            "trigger": "manual",
            "custom_instructions": "preserve the deployment constraints",
        },
        store=store,
        timestamp="2026-08-28T06:34:00Z",
    )
    post = claude_official_full_fidelity_events(
        {
            **_base("PostCompact"),
            "trigger": "manual",
            "compact_summary": "the exact provider generated summary",
        },
        store=store,
        timestamp="2026-08-28T06:34:01Z",
    )

    instruction = next(event for event in pre if event["relation"] == "OBSERVED_COMPACTION_INSTRUCTIONS")
    summary = next(event for event in post if event["relation"] == "OBSERVED_COMPACTION_SUMMARY")
    assert _load(tmp_path, instruction).decode("utf-8") == "preserve the deployment constraints"
    assert _load(tmp_path, summary).decode("utf-8") == "the exact provider generated summary"
    assert "preserve the deployment constraints" not in json.dumps(pre)
    assert "the exact provider generated summary" not in json.dumps(post)


def test_prompt_expansion_and_elicitation_content_are_stored_exactly(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    expansion = claude_official_full_fidelity_events(
        {
            **_base("UserPromptExpansion"),
            "expansion_type": "slash_command",
            "command_name": "example-skill",
            "command_args": "arg1 arg2",
            "command_source": "plugin",
            "prompt": "/example-skill arg1 arg2",
        },
        store=store,
        timestamp="2026-08-28T06:35:00Z",
    )
    elicitation = claude_official_full_fidelity_events(
        {
            **_base("ElicitationResult"),
            "mcp_server_name": "my-mcp-server",
            "elicitation_id": "elicit-123",
            "mode": "form",
            "action": "accept",
            "content": {"username": "alice"},
        },
        store=store,
        timestamp="2026-08-28T06:35:01Z",
    )

    prompt = next(event for event in expansion if event["relation"] == "OBSERVED_EXPANSION_PROMPT")
    args = next(event for event in expansion if event["relation"] == "OBSERVED_EXPANSION_ARGUMENTS")
    result = next(event for event in elicitation if event["relation"] == "OBSERVED_ELICITATION_CONTENT")
    assert _load(tmp_path, prompt).decode("utf-8") == "/example-skill arg1 arg2"
    assert _load(tmp_path, args).decode("utf-8") == "arg1 arg2"
    assert json.loads(_load(tmp_path, result)) == {"username": "alice"}
    assert "/example-skill arg1 arg2" not in json.dumps(expansion)
    assert "alice" not in json.dumps(elicitation)


def test_stop_background_registry_is_distinct_from_final_response(tmp_path: Path) -> None:
    events = claude_official_full_fidelity_events(
        {
            **_base("Stop"),
            "stop_hook_active": False,
            "last_assistant_message": "main final",
            "background_tasks": [{"id": "bg-1", "status": "running"}],
            "session_crons": [{"id": "cron-1"}],
        },
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T06:36:00Z",
    )

    final = next(event for event in events if event["relation"] == "PRODUCED_ASSISTANT_RESPONSE")
    background = next(event for event in events if event["relation"] == "OBSERVED_BACKGROUND_TASKS")
    crons = next(event for event in events if event["relation"] == "OBSERVED_SESSION_CRONS")
    assert _load(tmp_path, final).decode("utf-8") == "main final"
    assert json.loads(_load(tmp_path, background))[0]["id"] == "bg-1"
    assert json.loads(_load(tmp_path, crons))[0]["id"] == "cron-1"


def test_cli_combines_official_semantics_and_content(monkeypatch, tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {
        **_base("PostCompact"),
        "cwd": str(tmp_path),
        "trigger": "auto",
        "compact_summary": "provider summary",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert claude_hook_main(["--sidecar", str(sidecar)]) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = {record["relation"] for record in records}
    assert "COMPACTED_CONTEXT" in relations
    assert "OBSERVED_COMPACTION_SUMMARY" in relations
    assert "OBSERVED_PROVIDER_METADATA" in relations
    assert "provider summary" not in json.dumps(records)
