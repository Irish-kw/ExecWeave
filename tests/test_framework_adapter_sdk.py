from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.framework_adapters import (
    AdapterContext,
    AutoGenAdapter,
    CAMELAdapter,
    ContentCapturePolicy,
    MetaGPTAdapter,
    ProcessRef,
    default_registry,
    stable_id,
)


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_stable_id_does_not_use_time_or_content() -> None:
    assert stable_id("agent", "worker-a", framework="camel", run_id="run-1") == stable_id(
        "agent", "worker-a", framework="camel", run_id="run-1"
    )
    assert stable_id("agent", "worker-a", framework="camel", run_id="run-1") != stable_id(
        "agent", "worker-b", framework="camel", run_id="run-1"
    )


def test_registry_has_builtin_adapters_without_framework_imports() -> None:
    registry = default_registry(discover=False)
    assert registry.names() == ("autogen", "camel", "metagpt")
    assert registry.create("camel", AdapterContext(framework="camel")).__class__ is CAMELAdapter
    assert registry.create("metagpt", AdapterContext(framework="metagpt")).__class__ is MetaGPTAdapter


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


def test_metadata_only_is_explicit_and_does_not_create_content(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="camel",
        run_id="run-1",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("metadata_only"),
    )
    adapter = CAMELAdapter(context)
    agent = adapter.agent_created("coordinator", name="Coordinator")
    adapter.message("m-1", agent, None, content="private prompt", role="user")

    records = _records(tmp_path / "semantic.jsonl")
    assert any(record["event_type"] == "MESSAGE_SENT" for record in records)
    message = next(record for record in records if record["event_type"] == "MESSAGE_SENT")
    attributes = message["attributes"]
    assert attributes["capture_mode"] == "metadata_only"
    assert attributes["content_available"] is False
    assert not (tmp_path / "content").exists()


def test_prompt_and_response_are_separate_content_refs_and_reasoning_is_blocked(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="metagpt",
        run_id="run-1",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
        process=ProcessRef(1234, 42.0, "python.exe"),
    )
    adapter = MetaGPTAdapter(context)
    role = adapter.observe_role("product-manager", name="Product Manager", role="planner")
    task = adapter.observe_task("task-1", owner=role, status="created")
    adapter.observe_message("m-1", source=role, target=None, content="build a report", role="user")
    adapter.observe_model_call("call-1", role=role, model_id="llama3.1:8b", request="prompt", status="request", task_id=task.id)
    adapter.observe_model_call("call-1", role=role, model_id="llama3.1:8b", response="answer", status="response")
    adapter.context.content.put_text("should not persist", content_kind="hidden_reasoning")

    records = _records(tmp_path / "semantic.jsonl")
    assert any(record["event_type"] == "MODEL_REQUEST" for record in records)
    assert any(record["event_type"] == "MODEL_RESPONSE" for record in records)
    assert any(record["relation"] == "CORRELATED_WITH_PROCESS" for record in records)
    assert all("authorization" not in json.dumps(record).lower() for record in records)
    files = list((tmp_path / "content").rglob("*"))
    assert len([path for path in files if path.is_file()]) == 3


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
        owner=owner,
        name="Framework acceptance task",
        content=prompt,
    ) if framework != "camel" else getattr(adapter, task_method)(
        "task-1",
        name="Framework acceptance task",
        owner=owner,
        content=prompt,
    )

    records = _records(tmp_path / framework / "semantic.jsonl")
    content = next(
        record for record in records
        if record["event_type"] == "TASK_CONTENT_RECORDED"
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


def test_credentials_are_removed_from_entity_metadata(tmp_path: Path) -> None:
    context = AdapterContext(framework="camel", sidecar=tmp_path / "semantic.jsonl")
    agent = context.entity("agent", "a", attributes={"authorization": "secret", "nested": {"token": "secret", "safe": True}})
    context.emit("AGENT_CREATED", "AGENT_CREATED", source=agent)
    payload = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    assert "secret" not in payload
    assert '"safe":true' in payload


def test_invalid_event_type_fails_closed(tmp_path: Path) -> None:
    context = AdapterContext(framework="camel", sidecar=tmp_path / "semantic.jsonl")
    with pytest.raises(ValueError, match="unsupported canonical event"):
        context.emit("NOT_A_CANONICAL_EVENT", "UNKNOWN", attributes={})
