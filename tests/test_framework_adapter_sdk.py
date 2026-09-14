from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.framework_adapters import (
    AdapterContext,
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
