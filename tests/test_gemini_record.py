from __future__ import annotations

import os
import sys
from pathlib import Path

from execweave.gemini_record import record_gemini_to_viewer
from execweave.graph_ops import load_graph
from execweave.validate import validate_event_stream


def _hook_emitter_code(cwd: Path) -> str:
    base = {
        "cwd": str(cwd),
        "session_id": "gemini-test-session",
        "transcript_path": str(cwd / "transcript.json"),
    }
    return (
        "import json, subprocess; "
        "from datetime import datetime, timezone; "
        f"base={base!r}; "
        "now=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00','Z'); "
        "payloads=["
        "{**base,'hook_event_name':'SessionStart','timestamp':now(),'source':'startup'},"
        "{**base,'hook_event_name':'BeforeTool','timestamp':now(),'tool_name':'run_shell_command','tool_input':{'command':'echo execweave-gemini-record'}},"
        "{**base,'hook_event_name':'AfterTool','timestamp':now(),'tool_name':'run_shell_command','tool_input':{'command':'echo execweave-gemini-record'},'tool_response':{'returnDisplay':'execweave-gemini-record','error':None}}]; "
        "[(subprocess.run(['execweave-gemini-hook'], input=json.dumps(p), text=True, check=True, capture_output=True)) for p in payloads]"
    )


def test_gemini_record_binds_sidecar_and_builds_layered_artifacts(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "gemini-run"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "parent-value-must-be-restored")
    result = record_gemini_to_viewer(
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
    assert result.merged_event_stream is not None and validate_event_stream(result.merged_event_stream).valid
    assert result.correlated_event_stream is not None and validate_event_stream(result.correlated_event_stream).valid
    assert result.semantic_graph is not None and result.semantic_graph.exists()
    assert result.correlated_graph is not None and result.correlated_graph.exists()
    assert result.correlated_viewer is not None and result.correlated_viewer.exists()
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-value-must-be-restored"
    graph = load_graph(result.semantic_graph)
    relations = {edge["relation"] for edge in graph["edges"]}
    assert {"STARTED_PROVIDER_SESSION", "REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_COMMAND", "TOOL_RESULT_RETURNED"}.issubset(relations)
    assert result.correlation is not None
    assert result.correlation.tool_calls_considered == 1
    assert result.correlation.skipped_unsupported == 1


def test_gemini_record_without_hooks_falls_back_to_runtime(tmp_path: Path) -> None:
    result = record_gemini_to_viewer(
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
