from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from execweave.framework_adapters import (
    AdapterContext,
    CAMELAdapter,
    ContentCapturePolicy,
    ProcessRef,
)


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_camel_unrouted_callback_is_connected_to_process_boundary(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="camel",
        run_id="run-4b",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
        process=ProcessRef(4321, 123.0, "python.exe"),
    )
    adapter = CAMELAdapter(context)
    adapter._callback_event(
        "log_message",
        (SimpleNamespace(message="task completed"),),
        {},
    )

    records = _records(tmp_path / "semantic.jsonl")
    boundary = next(
        record for record in records if record["event_type"] == "MESSAGE_UNROUTED"
    )
    assert boundary["relation"] == "OBSERVED_AT_PROCESS"
    assert boundary["source"]["type"] == "message"
    assert boundary["target"]["type"] == "process_reference"
    assert boundary["attributes"]["routing_status"] == "unrouted"
    assert boundary["attributes"]["missing_sender"] is True
    assert boundary["attributes"]["missing_recipient"] is True


def test_camel_root_task_can_be_owned_by_configured_coordinator(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="camel",
        run_id="run-4c",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
    )
    adapter = CAMELAdapter(context)
    coordinator = adapter.agent_created("coordinator", name="Coordinator")
    task = adapter.task_created(
        "root",
        name="root task",
        owner=coordinator,
        ownership_basis="configured_coordinator",
    )

    records = _records(tmp_path / "semantic.jsonl")
    created = next(
        record
        for record in records
        if record["event_type"] == "TASK_CREATED"
        and record["target"]["id"] == task.id
    )
    assert created["source"]["id"] == coordinator.id
