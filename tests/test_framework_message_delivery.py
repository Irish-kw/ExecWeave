from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from execweave.framework_adapters import AdapterContext, CAMELAdapter, ContentCapturePolicy, MetaGPTAdapter
from test_execution_flow_integrity import _edge, _project
from test_session_execution_flow import _graph


@pytest.mark.parametrize("framework", ("camel", "autogen", "metagpt"))
def test_framework_chat_completion_response_is_visible(framework):
    from execweave.conversation_preview_generic import _generic_content_messages

    messages = _generic_content_messages(
        {"choices": [{"message": {"role": "assistant", "content": "Actual response"}}]},
        content_kind=f"{framework}.model_response", timestamp=None, ordinal=1,
        identity={"agent_path": "/worker", "is_root": False},
    )
    assert len(messages) == 1
    assert messages[0]["text"] == "Actual response"
    assert messages[0]["sender"] == "/worker"
    assert messages[0]["kind"] == "assistant_message"


def test_metagpt_action_lifecycle_does_not_replace_assigned_prompt():
    from execweave.viewer_semantic_projection import collapse_framework_tasks

    nodes = [
        {"id": "root", "type": "agent", "attributes": {"conversation_scope": "framework_agent"}},
        {"id": "task", "type": "task", "attributes": {"task_prompt": "Ask both workers"}},
        {"id": "action", "type": "task", "name": "MetaGPT action", "attributes": {"action": True}},
    ]
    edges = [_edge("task", "root", "task", "TASK_CREATED", 1), _edge("act", "root", "action", "TASK_STARTED", 99)]
    projected, _, _ = collapse_framework_tasks(nodes, edges)
    root = next(node for node in projected if node["id"] == "root")
    assert root["attributes"]["viewer_assigned_task_prompt"] == "Ask both workers"
    assert root["attributes"]["viewer_assigned_task_ids"] == ["task", "action"]


def _context(tmp_path, framework):
    return AdapterContext(framework=framework, run_id="test", sidecar=tmp_path / "semantic.jsonl",
                          content_root=tmp_path, capture_policy=ContentCapturePolicy("prompt_and_response"))


def test_camel_channel_records_both_receipts_and_does_not_patch_other_instances(tmp_path):
    class Channel:
        async def post_task(self, task, publisher_id, assignee_id):
            self.task = task

        async def get_assigned_task_by_assignee(self, assignee_id):
            return self.task

        async def return_task(self, task_id):
            return None

        async def get_returned_task_by_publisher(self, publisher_id):
            return self.task

    adapter = CAMELAdapter(_context(tmp_path, "camel"))
    root = adapter.agent_created("main")
    adapter.agent_created("worker")
    other = Channel()
    channel = adapter.observe_task_channel(Channel(), publishers={"native-main": root})
    assert adapter.observe_task_channel(channel, publishers={"native-main": root}) is channel
    assert other.post_task.__func__ is Channel.post_task

    async def exchange():
        task = SimpleNamespace(id="task", content="requested check", result="")
        await channel.post_task(task, "native-main", "worker")
        assert await channel.get_assigned_task_by_assignee("worker") is task
        task.result = "completed check"
        await channel.return_task(task.id)
        assert await channel.get_returned_task_by_publisher("native-main") is task

    asyncio.run(exchange())
    records = [json.loads(line) for line in (tmp_path / "semantic.jsonl").read_text().splitlines()]
    deliveries = [r for r in records if r["event_type"] == "MESSAGE_RECEIVED"]
    assert len(deliveries) == 2
    assert deliveries[0]["source"]["id"] == root.id
    assert deliveries[1]["target"]["id"] == root.id
    assert deliveries[0]["attributes"]["message_id"] != deliveries[1]["attributes"]["message_id"]
    for event in deliveries:
        assert event["attributes"]["routing_source"] == "camel_task_channel_delivery"


def test_metagpt_delivery_uses_actual_receiving_role_not_broadcast_targets(tmp_path):
    adapter = MetaGPTAdapter(_context(tmp_path, "metagpt"))
    root = adapter.observe_role("main")
    actual = adapter.observe_role("actual")
    adapter.observe_role("other")
    message = SimpleNamespace(id="native-message", sent_from="main", send_to={"actual", "other"}, content="check", role="agent")
    adapter.observe_message_delivery(message, recipient=actual)
    records = [json.loads(line) for line in (tmp_path / "semantic.jsonl").read_text().splitlines()]
    receipt = next(r for r in records if r["event_type"] == "MESSAGE_RECEIVED")
    assert receipt["source"]["id"] == root.id
    assert receipt["target"]["id"] == actual.id
    assert len([r for r in records if r["event_type"] == "MESSAGE_RECEIVED"]) == 1


@pytest.mark.parametrize("framework", ("camel", "autogen", "metagpt"))
def test_framework_message_paths_preserve_recipient_and_return(framework):
    graph = _graph(framework)
    for node in graph["nodes"]:
        if node["type"] == "agent":
            node["attributes"]["conversation_scope"] = "framework_agent"
    graph["edges"] = [e for e in graph["edges"] if e["id"] != "reply"] + [
        _edge("send", "root", "child", "MESSAGE_SENT", 3),
        _edge("receive", "root", "child", "MESSAGE_RECEIVED", 4),
        _edge("return", "child", "root", "MESSAGE_RECEIVED", 9),
    ]
    result = _project(graph)
    messages = [n for n in result["nodes"] if n.get("attributes", {}).get("viewer_framework_messages")]
    assert len(messages) == 2
    for node in messages:
        recipient = node["attributes"]["recipient_agent_id"]
        assert any(e["source"] == node["id"] and e["target"] == recipient and e["relation"] == "DELIVERED_AGENT_MESSAGE" for e in result["edges"])
    back = next(n for n in messages if n["attributes"]["recipient_agent_id"] == "root")
    assert any(e["source"] == "child" and e["target"] == back["id"] for e in result["edges"])


def test_addressed_message_does_not_claim_observed_delivery():
    graph = _graph("camel")
    for n in graph["nodes"]:
        if n["type"] == "agent":
            n["attributes"]["conversation_scope"] = "framework_agent"
    graph["edges"].append(_edge("send", "root", "child", "MESSAGE_SENT", 3))
    result = _project(graph)
    node = next(n for n in result["nodes"] if n.get("attributes", {}).get("viewer_framework_messages"))
    assert any(e["source"] == node["id"] and e["relation"] == "ADDRESSED_TO" for e in result["edges"])
    assert not any(e["source"] == node["id"] and e["relation"] == "DELIVERED_AGENT_MESSAGE" for e in result["edges"])
