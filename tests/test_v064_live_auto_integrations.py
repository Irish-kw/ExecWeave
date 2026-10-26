from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from execweave.claude_hook_cli import main as claude_hook_main
from execweave.codex_hook_cli import main as codex_hook_main
from execweave.cursor_hook_cli import main as cursor_hook_main
from execweave.live import _LiveState
from execweave.opencode_hook_cli import main as opencode_hook_main


def _write_runtime(path: Path) -> None:
    records = [
        {
            "schema_version": "0.2",
            "event_id": "start",
            "session_id": "live-session",
            "timestamp": "2026-08-26T00:00:00Z",
            "sequence": 1,
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": {"id": "agent:test", "type": "agent", "name": "test"},
            "target": {
                "id": "session:live-session",
                "type": "session",
                "name": "live-session",
            },
            "attributes": {"backend": "portable", "causal": True},
        }
    ]
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _invoke_hook(monkeypatch, main, payload: dict[str, object]) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert main([]) == 0


def test_configured_agent_integrations_inherit_live_sidecar_and_stream_into_viewer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))

    _invoke_hook(
        monkeypatch,
        claude_hook_main,
        {
            "session_id": "claude-session",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "model": "claude-sonnet",
        },
    )
    _invoke_hook(
        monkeypatch,
        codex_hook_main,
        {
            "session_id": "codex-session",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "model": "gpt-test",
            "source": "startup",
        },
    )
    _invoke_hook(
        monkeypatch,
        cursor_hook_main,
        {
            "conversation_id": "cursor-conversation",
            "generation_id": "cursor-generation",
            "session_id": "cursor-session",
            "hook_event_name": "sessionStart",
            "cwd": str(tmp_path),
            "workspace_roots": [str(tmp_path)],
            "model": "claude-sonnet",
            "model_id": "claude-sonnet-test",
        },
    )
    _invoke_hook(
        monkeypatch,
        opencode_hook_main,
        {
            "hook_event_name": "chat.message",
            "sessionID": "opencode-session",
            "messageID": "message-1",
            "agent": "build",
            "model": {"providerID": "openrouter", "modelID": "gpt-test"},
            "cwd": str(tmp_path),
        },
    )

    assert sidecar.exists()
    raw_records = [
        json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    providers = {
        record.get("attributes", {}).get("provider")
        for record in raw_records
        if isinstance(record.get("attributes"), dict)
    }
    assert {"claude", "codex", "cursor", "opencode"}.issubset(providers)

    runtime = tmp_path / "events.jsonl"
    _write_runtime(runtime)
    state = _LiveState("live-session", runtime, sidecar)
    graph = state.snapshot()

    assert graph["live_evidence_counts"]["os_runtime"] == 1
    assert graph["live_evidence_counts"]["specialized"] >= 5
    assert graph["live_specialized_provisional"] is True
    graph_providers = {
        node.get("attributes", {}).get("provider")
        for node in graph["nodes"]
        if isinstance(node.get("attributes"), dict)
    }
    assert {"claude", "codex", "cursor", "opencode"}.issubset(graph_providers)
