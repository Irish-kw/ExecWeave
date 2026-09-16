from __future__ import annotations

from copy import deepcopy
import json
import os
import sys
from pathlib import Path

import pytest

from execweave.framework_adapters import (
    AdapterContext,
    AutoGenAdapter,
    CAMELAdapter,
    ContentCapturePolicy,
    MetaGPTAdapter,
)
from execweave.graph_ops import load_graph
from execweave.live import run_live
from execweave.viewer_agent_panel import _AGENT_PANEL_JS
from execweave.workflow import record_to_viewer


def _records(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_framework_agent_panel_projects_assigned_task_and_communication() -> None:
    source = _AGENT_PANEL_JS
    assert "function execweaveAssignedTaskText(agent)" in source
    assert "const exactAssignment=['ASSIGNED','AGENT','TASK'].join('_')" in source
    assert "['ASSIGNED_TO',exactAssignment]" in source
    assert "String(edge.relation||'')==='TASK_CREATED'" in source
    assert "String(edge.relation||'')==='TASK_STARTED'" in source
    assert "direct.at(-1)||owned.at(-1)||started.at(-1)" in source
    assert "execweaveFillAssignedTask" in source
    assert "viewer_assigned_task_prompt" in source
    assert "attrs(node).conversation_scope==='framework_agent'" in source
    assert "card('Agent communication',frameworkCommunication)" in source


def test_framework_tasks_are_projected_into_agents_like_provider_dashboards() -> None:
    from execweave.viewer_projection import project_viewer_graph

    prompt = "Framework task prompt belongs in the assigned agent inspector."
    task_id = "task:framework:task-1"
    content_id = "observed-content:framework-task"
    agent_id = "agent:framework:worker"
    graph = {
        "graph_schema_version": "0.2",
        "event_count": 4,
        "nodes": [
            {
                "id": agent_id,
                "type": "agent",
                "name": "Worker",
                "attributes": {
                    "provider": "camel",
                    "conversation_scope": "framework_agent",
                },
            },
            {
                "id": task_id,
                "type": "task",
                "name": "Framework acceptance task",
                "attributes": {
                    "provider": "camel",
                    "task_prompt": prompt,
                },
            },
            {
                "id": content_id,
                "type": "observed_content",
                "name": "camel.task_prompt",
                "attributes": {"provider": "camel"},
            },
        ],
        "edges": [
            {
                "id": "task-created",
                "source": agent_id,
                "target": task_id,
                "relation": "TASK_CREATED",
                "first_sequence": 1,
                "last_sequence": 1,
            },
            {
                "id": "task-assigned",
                "source": task_id,
                "target": agent_id,
                "relation": "ASSIGNED_TO",
                "first_sequence": 2,
                "last_sequence": 2,
            },
            {
                "id": "task-content",
                "source": task_id,
                "target": content_id,
                "relation": "HAS_TASK_CONTENT",
                "first_sequence": 3,
                "last_sequence": 3,
            },
        ],
        "node_count": 3,
        "edge_count": 3,
    }
    original = deepcopy(graph)

    projected = project_viewer_graph(graph)
    projected_ids = {node["id"] for node in projected["nodes"]}
    projected_edges = {
        (edge["source"], edge["relation"], edge["target"])
        for edge in projected["edges"]
    }
    agent = next(node for node in projected["nodes"] if node["id"] == agent_id)

    assert projected_ids == {agent_id}
    assert not projected_edges
    assert agent["attributes"]["viewer_assigned_task_id"] == task_id
    assert agent["attributes"]["viewer_assigned_task_prompt"] == prompt
    assert agent["attributes"]["viewer_assigned_task_count"] == 1
    assert projected["viewer_projection"]["framework_task_node_count"] == 1
    assert projected["viewer_projection"]["framework_task_content_node_count"] == 1
    assert graph == original


def test_environment_context_uses_shared_run_identity_and_current_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "runtime-run")
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "runtime-session")

    context = AdapterContext.from_environment("camel")

    assert context.run_id == "runtime-run"
    assert context.session_id == "runtime-session"
    assert context.process is not None
    assert context.process.pid == os.getpid()
    assert context.process.create_time is not None


@pytest.mark.parametrize(
    ("framework", "adapter_type", "agent_method", "task_method"),
    [
        ("camel", CAMELAdapter, "agent_created", "task_created"),
        ("autogen", AutoGenAdapter, "observe_agent", "observe_task"),
        ("metagpt", MetaGPTAdapter, "observe_role", "observe_task"),
    ],
)
def test_every_framework_task_records_its_prompt(
    tmp_path: Path,
    framework: str,
    adapter_type: type,
    agent_method: str,
    task_method: str,
) -> None:
    context = AdapterContext(
        framework=framework,
        run_id=f"{framework}-task-prompt",
        sidecar=tmp_path / framework / "semantic.jsonl",
        content_root=tmp_path / framework,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = adapter_type(context)
    owner = getattr(adapter, agent_method)("owner", name="Owner")
    prompt = f"{framework} must expose this task prompt in the dashboard."
    task = getattr(adapter, task_method)(
        "task-1",
        name="Framework acceptance task",
        owner=owner,
        content=prompt,
    )

    records = _records(tmp_path / framework / "semantic.jsonl")
    content = next(
        record for record in records if record["event_type"] == "TASK_CONTENT_RECORDED"
    )
    assert content["source"]["id"] == task.id
    assert content["relation"] == "HAS_TASK_CONTENT"
    created = next(record for record in records if record["event_type"] == "TASK_CREATED")
    assert created["target"]["attributes"]["task_prompt"] == prompt
    assert (tmp_path / framework / content["attributes"]["content_ref"]).read_text(
        encoding="utf-8"
    ) == prompt


@pytest.mark.parametrize(
    ("framework", "adapter_type", "task_method"),
    [
        ("camel", CAMELAdapter, "task_created"),
        ("autogen", AutoGenAdapter, "observe_task"),
        ("metagpt", MetaGPTAdapter, "observe_task"),
    ],
)
def test_content_ref_only_task_does_not_inline_prompt_metadata(
    tmp_path: Path,
    framework: str,
    adapter_type: type,
    task_method: str,
) -> None:
    context = AdapterContext(
        framework=framework,
        run_id=f"{framework}-content-ref-only",
        sidecar=tmp_path / framework / "semantic.jsonl",
        content_root=tmp_path / framework,
        capture_policy=ContentCapturePolicy("content_ref_only"),
    )
    adapter = adapter_type(context)
    getattr(adapter, task_method)("task", content="reference-only prompt")

    records = _records(tmp_path / framework / "semantic.jsonl")
    created = next(record for record in records if record["event_type"] == "TASK_CREATED")
    assert "task_prompt" not in created["target"]["attributes"]
    assert any(record["event_type"] == "TASK_CONTENT_RECORDED" for record in records)


def test_record_to_viewer_merges_framework_events_with_runtime_identity(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "framework-recording"
    source_root = Path(__file__).resolve().parents[1] / "src"
    code = f'''import os
import sys

sys.path.insert(0, {str(source_root)!r})
from execweave.framework_adapters import AdapterContext, CAMELAdapter

context = AdapterContext.from_environment("camel", capture_mode="prompt_and_response")
assert context.run_id == os.environ["EXECWEAVE_RUN_ID"]
assert context.session_id == os.environ["EXECWEAVE_SESSION_ID"]
assert context.process is not None
adapter = CAMELAdapter(context)
planner = adapter.agent_created("planner", name="Planner", role="planner")
worker = adapter.agent_created("worker", name="Worker", role="worker")
prompt = "Inspect the local Ollama endpoint and report completion."
task = adapter.task_created("task-1", name=prompt, content=prompt)
adapter.task_assigned(task, worker)
adapter.message("message-1", planner, worker, content="Planner to Worker: inspect the endpoint.", role="assistant", task=task)
adapter.model_call("call-1", worker, "llama3.1:8b", request={{"messages": [{{"role": "user", "content": prompt}}]}}, status="request", task=task)
adapter.model_call("call-1", worker, "llama3.1:8b", response={{"content": "completed"}}, status="response", task=task)
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
    semantic_records = _records(result.semantic_sidecar)
    assert {record["attributes"]["session_id"] for record in semantic_records} == {
        result.session_id
    }
    assert any(record["relation"] == "CORRELATED_WITH_PROCESS" for record in semantic_records)

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
    assert "Inspect the local Ollama endpoint" in result.viewer.read_text(encoding="utf-8")


def test_record_to_viewer_without_semantics_and_restores_framework_environment(
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
    assert result.semantic_sidecar == (result.output_dir / "semantic.jsonl").resolve()
    assert result.materialized_event_stream == result.event_stream
    assert result.semantic_event_count == 0
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "parent-sidecar"
    assert os.environ["EXECWEAVE_RUN_ID"] == "parent-run"
    assert os.environ["EXECWEAVE_SESSION_ID"] == "parent-session"


def test_run_live_injects_and_restores_framework_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "keep-me")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "keep-run")
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "keep-session")
    code = """import os
assert os.environ['EXECWEAVE_RUN_ID'] == os.environ['EXECWEAVE_SESSION_ID']
assert os.environ['EXECWEAVE_SEMANTIC_SIDECAR'].endswith('semantic.jsonl')
"""
    result = run_live(
        [sys.executable, "-c", code],
        watch_root=tmp_path,
        output_dir=tmp_path / "live-environment",
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 0
    assert os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "keep-me"
    assert os.environ["EXECWEAVE_RUN_ID"] == "keep-run"
    assert os.environ["EXECWEAVE_SESSION_ID"] == "keep-session"
