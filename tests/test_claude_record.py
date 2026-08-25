from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from execweave.claude_record import record_claude_to_viewer
from execweave.graph_ops import load_graph
from execweave.validate import validate_event_stream


def _hook_emitter_code(cwd: Path) -> str:
    payload = {
        "session_id": "claude-test-session",
        "prompt_id": "prompt-1",
        "cwd": str(cwd),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "toolu-test",
        "tool_input": {"command": "echo execweave-claude-record"},
    }
    return (
        "import json, subprocess; "
        f"payload={payload!r}; "
        "subprocess.run(['execweave-claude-hook'], input=json.dumps(payload), "
        "text=True, check=True)"
    )


def test_claude_record_binds_hook_sidecar_and_builds_semantic_graph(
    tmp_path: Path, monkeypatch
) -> None:
    output_dir = tmp_path / "claude-run"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "parent-value-must-be-restored")

    result = record_claude_to_viewer(
        [sys.executable, "-c", _hook_emitter_code(tmp_path)],
        watch_root=tmp_path,
        output_dir=output_dir,
        backend="portable",
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.runtime.return_code == 0
    assert result.semantic_status == "merged"
    assert result.semantic_sidecar == (output_dir / "semantic.jsonl").resolve()
    assert result.semantic_sidecar.exists()
    assert result.merged_event_stream == (output_dir / "events.semantic.jsonl").resolve()
    assert result.semantic_graph == (output_dir / "graph.semantic.json").resolve()
    assert result.semantic_viewer == (output_dir / "viewer.semantic.html").resolve()
    assert result.merged_event_stream is not None and result.merged_event_stream.exists()
    assert result.semantic_graph is not None and result.semantic_graph.exists()
    assert result.semantic_viewer is not None and result.semantic_viewer.exists()
    assert result.correlation_status == "completed_no_matches"
    assert result.correlated_event_stream == (output_dir / "events.correlated.jsonl").resolve()
    assert result.correlated_graph == (output_dir / "graph.correlated.json").resolve()
    assert result.correlated_viewer == (output_dir / "viewer.correlated.html").resolve()
    assert result.correlated_event_stream.exists()
    assert result.correlated_graph.exists()
    assert result.correlated_viewer.exists()
    assert result.correlation is not None
    assert result.correlation.correlated_tool_calls == 0
    assert validate_event_stream(result.runtime.event_stream).valid is True
    assert validate_event_stream(result.merged_event_stream).valid is True
    assert validate_event_stream(result.correlated_event_stream).valid is True
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-value-must-be-restored"

    graph = load_graph(result.semantic_graph)
    relations = {edge["relation"] for edge in graph["edges"]}
    node_types = {node["type"] for node in graph["nodes"]}
    assert "REQUESTED_TOOL_CALL" in relations
    assert "USES_TOOL" in relations
    assert "DECLARED_COMMAND" in relations
    assert "tool_call" in node_types
    assert "command" in node_types

    correlated_graph = load_graph(result.correlated_graph)
    summary = correlated_graph["metadata"]["correlation"]
    assert summary["tool_calls_considered"] == result.correlation.tool_calls_considered
    assert summary["correlated_tool_calls"] == result.correlation.correlated_tool_calls
    assert summary["skipped_ambiguous"] == result.correlation.skipped_ambiguous
    assert summary["skipped_no_match"] == result.correlation.skipped_no_match
    assert summary["skipped_unsupported"] == result.correlation.skipped_unsupported
    assert summary["max_window_ms"] == result.correlation.max_window_ms
    viewer_html = result.correlated_viewer.read_text(encoding="utf-8")
    assert 'id="correlation-section"' in viewer_html
    assert '"correlation":{' in viewer_html


def test_claude_record_without_hook_events_falls_back_to_runtime_graph(tmp_path: Path) -> None:
    output_dir = tmp_path / "runtime-only"
    result = record_claude_to_viewer(
        [sys.executable, "-c", "print('no Claude hook here')"],
        watch_root=tmp_path,
        output_dir=output_dir,
        backend="portable",
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.runtime.return_code == 0
    assert result.semantic_status == "no_events"
    assert result.merged_event_stream is None
    assert result.semantic_graph is None
    assert result.semantic_viewer is None
    assert result.correlation_status == "not_run_no_semantic_events"
    assert result.correlated_event_stream is None
    assert result.correlated_graph is None
    assert result.correlated_viewer is None
    assert result.correlation is None
    assert result.runtime.graph.exists()
    assert result.runtime.viewer.exists()


def test_claude_record_restores_missing_environment_variable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    result = record_claude_to_viewer(
        [sys.executable, "-c", "print('runtime only')"],
        watch_root=tmp_path,
        output_dir=tmp_path / "restore-test",
        backend="portable",
        collect_filesystem=False,
        collect_network=False,
    )

    assert result.runtime.return_code == 0
    assert "EXECWEAVE_SEMANTIC_SIDECAR" not in os.environ


def test_claude_record_rejects_invalid_correlation_window_before_command(tmp_path: Path) -> None:
    marker = tmp_path / "should-not-run-invalid-window.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"

    with pytest.raises(ValueError, match="correlation_window_ms must be greater than zero"):
        record_claude_to_viewer(
            [sys.executable, "-c", code],
            watch_root=tmp_path,
            output_dir=tmp_path / "invalid-window",
            backend="portable",
            correlation_window_ms=0,
            collect_filesystem=False,
            collect_network=False,
        )

    assert not marker.exists()


def test_claude_record_preflight_rejects_semantic_conflict_before_command(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "semantic.jsonl").write_text("existing\n", encoding="utf-8")
    marker = tmp_path / "should-not-run.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"

    with pytest.raises(FileExistsError, match="Claude semantic artifacts already exist"):
        record_claude_to_viewer(
            [sys.executable, "-c", code],
            watch_root=tmp_path,
            output_dir=output_dir,
            backend="portable",
            collect_filesystem=False,
            collect_network=False,
        )

    assert not marker.exists()


def test_claude_record_preflight_rejects_correlated_conflict_before_command(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "existing-correlated"
    output_dir.mkdir()
    (output_dir / "events.correlated.jsonl").write_text("existing\n", encoding="utf-8")
    marker = tmp_path / "should-not-run-correlated.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"

    with pytest.raises(FileExistsError, match="Claude semantic artifacts already exist"):
        record_claude_to_viewer(
            [sys.executable, "-c", code],
            watch_root=tmp_path,
            output_dir=output_dir,
            backend="portable",
            collect_filesystem=False,
            collect_network=False,
        )

    assert not marker.exists()
