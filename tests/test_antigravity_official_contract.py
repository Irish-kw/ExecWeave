from __future__ import annotations

import io
import json
import sys

import pytest

from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.antigravity_hook_cli import (
    ANTIGRAVITY_OFFICIAL_HOOK_EVENTS,
    ANTIGRAVITY_PASSIVE_HOOK_EVENTS,
    antigravity_hook_config,
    main as antigravity_hook_main,
)
from execweave.content_store import FullFidelityContentStore


def _stop_payload(tmp_path, *, error: str = "") -> dict[str, object]:
    return {
        "executionNum": 2,
        "terminationReason": "model_stop" if not error else "error",
        "error": error,
        "fullyIdle": True,
        "conversationId": "conversation-stop",
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(tmp_path / "transcript.jsonl"),
        "artifactDirectoryPath": str(tmp_path / "artifacts"),
        "modelName": "gemini-test",
    }


def test_antigravity_official_surface_keeps_pre_tool_use_out_of_passive_default() -> None:
    assert set(ANTIGRAVITY_OFFICIAL_HOOK_EVENTS) == {
        "PreToolUse",
        "PostToolUse",
        "PreInvocation",
        "PostInvocation",
        "Stop",
    }
    assert set(ANTIGRAVITY_PASSIVE_HOOK_EVENTS) == {
        "PostToolUse",
        "PreInvocation",
        "PostInvocation",
        "Stop",
    }
    hook = antigravity_hook_config()["execweave-observability"]
    assert "PreToolUse" not in hook
    assert hook["Stop"][0]["command"].endswith("--event Stop")


def test_antigravity_stop_hook_is_fail_open_without_active_sidecar(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("must-not-be-read"))

    assert antigravity_hook_main(["--auto", "--event", "Stop"]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"decision": "stop"}
    assert captured.err == ""
    assert not (tmp_path / ".execweave").exists()


def test_antigravity_preinvocation_observes_session_without_claiming_session_start(
    tmp_path,
) -> None:
    payload = {
        "invocationNum": 3,
        "initialNumSteps": 10,
        "conversationId": "conversation-1",
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(tmp_path / "transcript.jsonl"),
        "artifactDirectoryPath": str(tmp_path / "artifacts"),
        "modelName": "gemini-test",
    }

    events = antigravity_hook_to_semantic_events(
        payload,
        hook_event="PreInvocation",
        timestamp="2026-08-28T08:00:00Z",
    )
    relations = {event["relation"] for event in events}

    assert "OBSERVED_PROVIDER_SESSION" in relations
    assert "INVOKES_MODEL" in relations
    assert "STARTED_PROVIDER_SESSION" not in relations
    observed = next(event for event in events if event["relation"] == "OBSERVED_PROVIDER_SESSION")
    assert observed["attributes"]["provider_contract_exact"] is True
    assert observed["attributes"]["antigravity_invocation_number"] == 3


def test_antigravity_stop_projects_exact_execution_state_without_inline_error(
    tmp_path,
) -> None:
    secret_error = "sensitive-provider-stop-error"
    payload = _stop_payload(tmp_path, error=secret_error)

    events = antigravity_hook_to_semantic_events(
        payload,
        hook_event="Stop",
        timestamp="2026-08-28T08:00:00Z",
    )
    stop = next(event for event in events if event["relation"] == "OBSERVED_EXECUTION_STOP")
    marker = next(event for event in events if event["relation"] == "OBSERVED_EXECUTION_ERROR")

    assert stop["target"]["type"] == "agent_execution"
    assert stop["target"]["id"] == "agent-execution:antigravity:conversation-stop:2"
    assert stop["target"]["attributes"]["execution_num"] == 2
    assert stop["target"]["attributes"]["termination_reason"] == "error"
    assert stop["target"]["attributes"]["fully_idle"] is True
    assert stop["attributes"]["provider_contract_exact"] is True
    assert marker["attributes"]["provider_reported_error"] is True
    assert secret_error not in json.dumps(events, sort_keys=True)


def test_antigravity_stop_requires_official_identity_fields(tmp_path) -> None:
    payload = _stop_payload(tmp_path)
    payload.pop("fullyIdle")

    with pytest.raises(ValueError, match="fullyIdle"):
        antigravity_hook_to_semantic_events(
            payload,
            hook_event="Stop",
            timestamp="2026-08-28T08:00:00Z",
        )


def test_antigravity_stop_error_is_content_addressed(tmp_path) -> None:
    secret_error = "sensitive-provider-stop-error"
    store = FullFidelityContentStore(tmp_path / "content-store")

    events = antigravity_hook_to_content_events(
        _stop_payload(tmp_path, error=secret_error),
        hook_event="Stop",
        store=store,
        timestamp="2026-08-28T08:00:00Z",
    )
    error_event = next(
        event for event in events if event["relation"] == "OBSERVED_EXECUTION_ERROR_CONTENT"
    )

    assert error_event["target"]["name"] == "antigravity.execution_stop_error"
    assert error_event["attributes"]["content_sha256"]
    assert error_event["attributes"]["content_path"].startswith("content/sha256/")
    assert secret_error not in json.dumps(events, sort_keys=True)
