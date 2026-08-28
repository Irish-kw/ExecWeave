from __future__ import annotations

import json
from pathlib import Path

import execweave.cursor_hook_cli as hook_cli


def test_missing_official_session_field_does_not_drop_adapter_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {
        "conversation_id": "cursor-conversation",
        "generation_id": "cursor-generation",
        "session_id": "cursor-session",
        "hook_event_name": "sessionStart",
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
        "model": "claude-test",
        "model_id": "claude-test-id",
    }
    monkeypatch.setattr(hook_cli, "read_hook_payload", lambda: payload)

    assert hook_cli.main(["--sidecar", str(sidecar)]) == 0

    records = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    relations = {record["relation"] for record in records}
    assert "USED_MODEL" in relations
    assert "OBSERVED_PROVIDER_METADATA" in relations
    assert "STARTED_PROVIDER_SESSION" not in relations


def test_missing_official_session_field_remains_an_error_in_strict_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {
        "conversation_id": "cursor-conversation",
        "generation_id": "cursor-generation",
        "session_id": "cursor-session",
        "hook_event_name": "sessionStart",
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
        "model_id": "claude-test-id",
    }
    monkeypatch.setattr(hook_cli, "read_hook_payload", lambda: payload)

    assert hook_cli.main(["--sidecar", str(sidecar), "--strict"]) == 1

    records = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    assert any(record["relation"] == "USED_MODEL" for record in records)
