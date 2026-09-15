from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from execweave.conversation_preview import conversation_preview
from execweave.conversation_records import conversation_record_entries
from execweave.framework_adapters import (
    AdapterContext,
    CAMELAdapter,
    AutoGenAdapter,
    ContentCapturePolicy,
    MetaGPTAdapter,
    ProcessRef,
)


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _graph(root: Path, records: list[dict[str, object]]) -> dict[str, object]:
    agents = {
        record["source"]["id"]: record["source"]
        for record in records
        if record["event_type"] == "AGENT_CREATED"
    }
    content_events = [
        record
        for record in records
        if record["event_type"] == "MESSAGE_CONTENT_RECORDED"
    ]
    nodes = list(agents.values()) + [content_events[0]["target"]]
    edges = [
        {
            "source": record["source"]["id"],
            "target": record["target"]["id"],
            "relation": record["relation"],
            "first_sequence": index,
            "last_sequence": index,
            "first_seen": record["timestamp"],
            "last_seen": record["timestamp"],
        }
        for index, record in enumerate(content_events, start=1)
    ]
    return {
        "source_path": str(root / "semantic.jsonl"),
        "nodes": nodes,
        "edges": edges,
    }


def test_routed_message_is_indexed_for_both_agents(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="autogen",
        run_id="run-1",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = AutoGenAdapter(context)
    sender = adapter.observe_agent("sender", name="Evidence")
    recipient = adapter.observe_agent("recipient", name="Summary")
    adapter.observe_message(
        "message-1",
        source=sender,
        target=recipient,
        content="Evidence -> Summary: completed",
        role="agent",
    )

    records = _records(tmp_path / "semantic.jsonl")
    content_events = [
        record
        for record in records
        if record["event_type"] == "MESSAGE_CONTENT_RECORDED"
    ]
    assert {record["source"]["id"] for record in content_events} == {
        sender.id,
        recipient.id,
    }
    assert len({record["target"]["id"] for record in content_events}) == 1

    entries = conversation_record_entries(_graph(tmp_path, records), tmp_path)
    assert {entry["conversation_preview"]["thread_id"] for entry in entries} == {
        "autogen:agent:sender",
        "autogen:agent:recipient",
    }
    for entry in entries:
        assert entry["conversation_preview"]["messages"][0]["text"] == (
            "Evidence -> Summary: completed"
        )


def test_model_context_is_attached_to_requesting_agent(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="autogen",
        run_id="run-2",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = AutoGenAdapter(context)
    agent = adapter.observe_agent("analyst", name="Analyst")
    adapter.observe_model_call(
        "call-1",
        agent=agent,
        model_id="llama3.1:8b",
        request={
            "messages": [
                {"role": "user", "content": "inspect the evidence"},
                {"role": "assistant", "source": "Planner", "content": "send summary"},
            ]
        },
        status="request",
    )

    records = _records(tmp_path / "semantic.jsonl")
    content_event = next(
        record
        for record in records
        if record["event_type"] == "MODEL_CONTENT_RECORDED"
    )
    assert content_event["source"]["id"] == agent.id
    preview = conversation_preview(
        tmp_path / content_event["attributes"]["content_ref"],
        content_kind=content_event["attributes"]["content_kind"],
        provider="autogen",
        source=content_event["source"],
    )
    assert preview is not None
    assert preview["thread_id"] == "autogen:agent:analyst"
    assert [message["text"] for message in preview["messages"]] == [
        "inspect the evidence",
        "send summary",
    ]


def test_metagpt_message_is_indexed_for_each_send_to_recipient(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="metagpt",
        run_id="run-3",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = MetaGPTAdapter(context)
    sender = adapter.observe_role("pm", name="ProductManager")
    engineer = adapter.observe_role("engineer", name="Engineer")
    reviewer = adapter.observe_role("reviewer", name="Reviewer")
    adapter.observe_message_object(
        SimpleNamespace(
            id="message-multicast",
            sent_from="pm",
            send_to=["engineer", "reviewer"],
            content="Please review the implementation",
            role="assistant",
            cause_by=None,
            metadata={},
        )
    )

    records = _records(tmp_path / "semantic.jsonl")
    content_events = [
        record
        for record in records
        if record["event_type"] == "MESSAGE_CONTENT_RECORDED"
    ]
    assert {record["source"]["id"] for record in content_events} == {
        sender.id,
        engineer.id,
        reviewer.id,
    }
    assert len({record["target"]["id"] for record in content_events}) == 1

    entries = conversation_record_entries(_graph(tmp_path, records), tmp_path)
    rich_entries = [entry for entry in entries if "conversation_preview" in entry]
    assert {entry["conversation_preview"]["thread_id"] for entry in rich_entries} == {
        "metagpt:agent:pm",
        "metagpt:agent:engineer",
        "metagpt:agent:reviewer",
    }
    for entry in rich_entries:
        assert entry["conversation_preview"]["messages"][0]["recipient"] == (
            "Engineer, Reviewer"
        )


def test_camel_missing_callback_ids_are_unique_and_explicitly_derived(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="camel",
        run_id="run-4",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    adapter.agent_created("worker", name="Worker")
    adapter._callback_event("log_message", (SimpleNamespace(message="one"),), {})
    adapter._callback_event("log_message", (SimpleNamespace(message="two"),), {})

    records = _records(tmp_path / "semantic.jsonl")
    messages = [
        record
        for record in records
        if record["event_type"] == "MESSAGE_SENT"
    ]
    assert len(messages) == 2
    assert messages[0]["target"]["id"] != messages[1]["target"]["id"]
    assert all(
        record["attributes"]["attributes"]["message_id_source"] == "execweave_derived"
        for record in messages
    )


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


def test_camel_callback_provider_route_is_indexed_for_both_agents(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="camel",
        run_id="run-5",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    sender = adapter.agent_created("sender", name="Evidence")
    recipient = adapter.agent_created("recipient", name="Summary")
    adapter._callback_event(
        "log_stream_chunk",
        (SimpleNamespace(worker_id="sender", target_worker_id="recipient", text="done"),),
        {},
    )

    records = _records(tmp_path / "semantic.jsonl")
    content_events = [
        record
        for record in records
        if record["event_type"] == "MESSAGE_CONTENT_RECORDED"
    ]
    assert {record["source"]["id"] for record in content_events} == {
        sender.id,
        recipient.id,
    }
