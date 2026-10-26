from __future__ import annotations

import os
import sys
from pathlib import Path

from execweave.graph_ops import load_graph
from execweave.opencode_record import record_opencode_to_viewer
from execweave.validate import validate_event_stream


def _plugin_emitter_code(cwd: Path) -> str:
    payloads = [
        {
            "hook_event_name": "chat.message",
            "sessionID": "opencode-test-session",
            "messageID": "message-1",
            "agent": "build",
            "model": {"providerID": "openrouter", "modelID": "openai/gpt-5.6-sol"},
            "cwd": str(cwd),
        },
        {
            "hook_event_name": "tool.execute.before",
            "sessionID": "opencode-test-session",
            "callID": "call-1",
            "tool": "bash",
            "args": {"command": "echo execweave-opencode-record"},
            "cwd": str(cwd),
        },
        {
            "hook_event_name": "tool.execute.after",
            "sessionID": "opencode-test-session",
            "callID": "call-1",
            "tool": "bash",
            "args": {"command": "echo execweave-opencode-record"},
            "cwd": str(cwd),
        },
    ]
    return (
        "import json, subprocess; "
        f"payloads={payloads!r}; "
        "[(subprocess.run(['execweave-opencode-hook'], input=json.dumps(p), "
        "text=True, check=True, capture_output=True)) for p in payloads]"
    )


def test_opencode_record_builds_layered_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "parent-value-must-be-restored")
    result = record_opencode_to_viewer(
        [sys.executable, "-c", _plugin_emitter_code(tmp_path)],
        watch_root=tmp_path,
        output_dir=tmp_path / "opencode-run",
        backend="portable",
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
    )
    assert result.runtime.return_code == 0
    assert result.semantic_status == "merged"
    assert result.merged_event_stream is not None
    assert validate_event_stream(result.merged_event_stream).valid
    assert result.correlated_event_stream is not None
    assert validate_event_stream(result.correlated_event_stream).valid
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-value-must-be-restored"
    assert result.semantic_graph is not None
    graph = load_graph(result.semantic_graph)
    relations = {edge["relation"] for edge in graph["edges"]}
    assert {
        "USED_MODEL",
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
        "TOOL_CALL_RETURNED",
    }.issubset(relations)
    assert result.correlation is not None
    assert result.correlation.tool_calls_considered == 1
    assert result.correlation.skipped_unsupported == 1


def test_opencode_record_without_plugin_falls_back_to_runtime(tmp_path: Path) -> None:
    result = record_opencode_to_viewer(
        [sys.executable, "-c", "print('runtime only')"],
        watch_root=tmp_path,
        output_dir=tmp_path / "runtime-only",
        backend="portable",
        collect_filesystem=False,
        collect_network=False,
    )
    assert result.semantic_status == "no_events"
    assert result.correlation_status == "not_run_no_semantic_events"
