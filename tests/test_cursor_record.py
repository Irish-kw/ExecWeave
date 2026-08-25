from __future__ import annotations

import os
import sys
from pathlib import Path

from execweave.cursor_record import record_cursor_to_viewer
from execweave.graph_ops import load_graph
from execweave.validate import validate_event_stream


def _hook_emitter_code(cwd: Path) -> str:
    base = {
        "conversation_id": "cursor-test-conversation",
        "generation_id": "cursor-test-generation",
        "session_id": "cursor-test-session",
        "cursor_version": "1.7.2",
        "cwd": str(cwd),
        "workspace_roots": [str(cwd)],
        "model": "claude-sonnet",
        "model_id": "claude-sonnet-4",
    }
    return (
        "import json, subprocess; "
        f"base={base!r}; "
        "payloads=["
        "{**base,'hook_event_name':'sessionStart'},"
        "{**base,'hook_event_name':'preToolUse','tool_name':'Shell','tool_use_id':'call-1','tool_input':{'command':'echo execweave-cursor-record','working_directory':base['cwd']}},"
        "{**base,'hook_event_name':'postToolUse','tool_name':'Shell','tool_use_id':'call-1','tool_input':{'command':'echo execweave-cursor-record'}}]; "
        "[(subprocess.run(['execweave-cursor-hook'], input=json.dumps(p), text=True, check=True, capture_output=True)) for p in payloads]"
    )


def test_cursor_record_binds_sidecar_and_builds_layered_artifacts(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "cursor-run"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "parent-value-must-be-restored")
    result = record_cursor_to_viewer(
        [sys.executable, "-c", _hook_emitter_code(tmp_path)],
        watch_root=tmp_path,
        output_dir=output_dir,
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
    assert result.semantic_graph is not None and result.semantic_graph.exists()
    assert result.correlated_graph is not None and result.correlated_graph.exists()
    assert result.correlated_viewer is not None and result.correlated_viewer.exists()
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-value-must-be-restored"
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


def test_cursor_record_without_hooks_falls_back_to_runtime(tmp_path: Path) -> None:
    result = record_cursor_to_viewer(
        [sys.executable, "-c", "print('runtime only')"],
        watch_root=tmp_path,
        output_dir=tmp_path / "runtime-only",
        backend="portable",
        collect_filesystem=False,
        collect_network=False,
    )
    assert result.semantic_status == "no_events"
    assert result.correlation_status == "not_run_no_semantic_events"
    assert result.runtime.graph.exists()
    assert result.runtime.viewer.exists()
