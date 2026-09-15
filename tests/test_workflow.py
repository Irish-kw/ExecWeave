import json
import sys
from pathlib import Path

import pytest

from execweave.graph_ops import load_graph
from execweave.validate import validate_event_stream
from execweave.workflow import record_to_viewer


def test_record_to_viewer_portable_end_to_end(tmp_path: Path) -> None:
    output_dir = tmp_path / "recording"
    result = record_to_viewer(
        [sys.executable, "-c", "print('execweave record test')"],
        watch_root=tmp_path,
        output_dir=output_dir,
        backend="portable",
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.return_code == 0
    assert result.output_dir == output_dir.resolve()
    assert result.event_stream == (output_dir / "events.jsonl").resolve()
    assert result.fidelity == (output_dir / "fidelity.json").resolve()
    assert result.graph == (output_dir / "graph.json").resolve()
    assert result.viewer == (output_dir / "viewer.html").resolve()
    assert result.event_stream.exists()
    assert result.fidelity.exists()
    assert result.graph.exists()
    assert result.viewer.exists()
    assert result.semantic_sidecar == (output_dir / "semantic.jsonl").resolve()
    assert result.materialized_event_stream == result.event_stream
    assert result.semantic_event_count == 0

    validation = validate_event_stream(result.event_stream)
    assert validation.valid is True
    graph = load_graph(result.graph)
    fidelity = json.loads(result.fidelity.read_text(encoding="utf-8"))
    assert graph["session_id"] == result.session_id
    assert graph["event_count"] == result.event_count
    assert graph["node_count"] == result.node_count
    assert graph["edge_count"] == result.edge_count
    assert fidelity == graph["fidelity"]
    assert fidelity["fidelity_schema_version"] == "0.1"
    assert fidelity["capture_context"]["platform"] == sys.platform
    assert fidelity["capture_context"]["configured_process_poll_interval_ms"] == 50.0
    assert fidelity["capture_context"]["filesystem_requested"] is False
    assert fidelity["capture_context"]["filesystem_collected"] is False
    assert fidelity["capture_context"]["filesystem_scope_downgraded"] is False
    assert fidelity["capture_context"]["network_requested"] is False
    assert fidelity["capture_context"]["network_collected"] is False
    assert "byte_level_dataflow" in fidelity["claims_not_supported"]
    assert "ExecWeave" in result.viewer.read_text(encoding="utf-8")


def test_record_to_viewer_merges_framework_adapter_events_with_runtime_identity(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "framework-recording"
    source_root = Path(__file__).resolve().parents[1] / "src"
    code = f'''import os
import sys

sys.path.insert(0, {str(source_root)!r})
from execweave.framework_adapters import AdapterContext, CAMELAdapter

context = AdapterContext.from_environment(
    "camel",
    capture_mode="prompt_and_response",
)
assert context.run_id == os.environ["EXECWEAVE_RUN_ID"]
assert context.session_id == os.environ["EXECWEAVE_SESSION_ID"]
assert context.process is not None
adapter = CAMELAdapter(context)
planner = adapter.agent_created("planner", name="Planner", role="planner")
worker = adapter.agent_created("worker", name="Worker", role="worker")
prompt = "Inspect the local Ollama endpoint and report completion."
task = adapter.task_created("task-1", name=prompt, content=prompt)
adapter.task_assigned(task, worker)
adapter.message(
    "message-1",
    planner,
    worker,
    content="Planner to Worker: inspect the endpoint.",
    role="assistant",
    task=task,
)
adapter.model_call(
    "call-1",
    worker,
    "llama3.1:8b",
    request={{"messages": [{{"role": "user", "content": prompt}}]}},
    status="request",
    task=task,
)
adapter.model_call(
    "call-1",
    worker,
    "llama3.1:8b",
    response={{"content": "completed"}},
    status="response",
    task=task,
)
'''

    result = record_to_viewer(
        [sys.executable, "-c", code],
        watch_root=tmp_path,
        output_dir=output_dir,
        backend="portable",
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.return_code == 0
    assert result.semantic_sidecar == (output_dir / "semantic.jsonl").resolve()
    assert result.materialized_event_stream == (
        output_dir / "events.semantic.jsonl"
    ).resolve()
    assert result.semantic_event_count > 0
    semantic_records = [
        json.loads(line)
        for line in result.semantic_sidecar.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert {
        record["attributes"]["session_id"] for record in semantic_records
    } == {result.session_id}
    assert any(
        record["relation"] == "CORRELATED_WITH_PROCESS"
        for record in semantic_records
    )

    graph = load_graph(result.graph)
    node_types = {node["type"] for node in graph["nodes"]}
    relations = {edge["relation"] for edge in graph["edges"]}
    assert {"agent", "task", "model", "observed_content", "process"} <= node_types
    assert "process_reference" not in node_types
    assert {
        "ASSIGNED_TO",
        "CORRELATED_WITH_PROCESS",
        "HAS_TASK_CONTENT",
        "HAS_MESSAGE_CONTENT",
        "HAS_MODEL_CONTENT",
        "REQUESTS_MODEL_CALL",
        "MODEL_CALL_RESPONDS",
    } <= relations
    assert "Inspect the local Ollama endpoint" in result.viewer.read_text(
        encoding="utf-8"
    )


def test_record_to_viewer_restores_framework_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "parent-sidecar")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "parent-run")
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "parent-session")

    result = record_to_viewer(
        [sys.executable, "-c", "pass"],
        watch_root=tmp_path,
        output_dir=tmp_path / "environment-recording",
        backend="portable",
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.return_code == 0
    assert __import__("os").environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-sidecar"
    assert __import__("os").environ["EXECWEAVE_RUN_ID"] == "parent-run"
    assert __import__("os").environ["EXECWEAVE_SESSION_ID"] == "parent-session"


def test_record_to_viewer_preserves_nonzero_command_exit(tmp_path: Path) -> None:
    output_dir = tmp_path / "failed-recording"
    result = record_to_viewer(
        [sys.executable, "-c", "raise SystemExit(7)"],
        watch_root=tmp_path,
        output_dir=output_dir,
        backend="portable",
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )

    assert result.return_code == 7
    assert validate_event_stream(result.event_stream).valid is True
    assert result.fidelity.exists()
    assert result.graph.exists()
    assert result.viewer.exists()


def test_record_preflight_rejects_conflicts_before_agent_runs(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text("old graph", encoding="utf-8")
    marker = tmp_path / "should-not-exist.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"

    with pytest.raises(FileExistsError, match="record artifacts already exist"):
        record_to_viewer(
            [sys.executable, "-c", code],
            watch_root=tmp_path,
            output_dir=output_dir,
            backend="portable",
            collect_filesystem=False,
            collect_network=False,
        )

    assert not marker.exists()
