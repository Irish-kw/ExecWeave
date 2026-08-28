from __future__ import annotations

import hashlib
import json
from pathlib import Path

from execweave.codex_hook_cli import _codex_trace_visibility_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import codex_conversation_archive_events
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator
from execweave.viewer_projection import write_graph_html


def test_codex_archive_preserves_complete_rollout_bytes_and_dashboard_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    sessions = codex_home / "sessions" / "2026" / "08" / "28"
    sessions.mkdir(parents=True)

    parent_thread = "root-thread"
    child_thread = "child-thread"
    rollout = sessions / f"rollout-2026-08-28T00-00-00-{child_thread}.jsonl"
    records = [
        {
            "timestamp": "2026-08-28T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": child_thread,
                "parent_thread_id": parent_thread,
                "agent_path": "/root/nightfood_b",
                "agent_nickname": "Banach",
                "subagent_history_start_ordinal": 1,
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": parent_thread,
                            "agent_path": "/root/nightfood_b",
                            "agent_nickname": "Banach",
                        }
                    }
                },
            },
        },
        {
            "timestamp": "2026-08-28T00:00:01Z",
            "ordinal": 1,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "commentary",
                "content": [
                    {
                        "type": "output_text",
                        "text": "我會先核對今晚可吃到的店與營業時段，再依口味整理短名單。",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-08-28T00:00:02Z",
            "ordinal": 2,
            "type": "response_item",
            "payload": {
                "type": "agent_message",
                "author": "/root/nightfood_a",
                "recipient": "/root/nightfood_b",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Message Type: MESSAGE\nSender: /root/nightfood_a\nPayload:\n",
                    },
                    {
                        "type": "encrypted_content",
                        "encrypted_content": "opaque-provider-ciphertext",
                    },
                ],
            },
        },
        {
            "timestamp": "2026-08-28T00:00:03Z",
            "ordinal": 3,
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "namespace": "collaboration",
                "name": "send_message",
                "arguments": json.dumps(
                    {
                        "target": "/root",
                        "message": "gAAAAA-provider-ciphertext",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-08-28T00:00:04Z",
            "ordinal": 4,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [
                    {
                        "type": "output_text",
                        "text": "已與顧問 A 收斂：首選小李子清粥小菜，備案東引小吃店。",
                    }
                ],
            },
        },
    ]
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    ).encode("utf-8")
    rollout.write_bytes(payload)

    store = FullFidelityContentStore(tmp_path / "run")
    events = codex_conversation_archive_events(
        {
            "hook_event_name": "SubagentStop",
            "session_id": parent_thread,
            "agent_id": child_thread,
            "agent_type": "default",
            "transcript_path": str(rollout),
        },
        store=store,
        timestamp="2026-08-28T00:00:05Z",
    )

    assert len(events) == 1
    assert events[0]["source"]["id"] == f"agent:codex:{parent_thread}:subagent:{child_thread}"
    assert events[0]["source"]["name"] == "/root/nightfood_b"
    assert events[0]["source"]["attributes"]["agent_nickname"] == "Banach"

    target = events[0]["target"]
    attributes = target["attributes"]
    archived = store.run_root / attributes["path"]
    assert archived.read_bytes() == payload
    assert attributes["size_bytes"] == len(payload)
    assert attributes["sha256"] == hashlib.sha256(payload).hexdigest()
    assert attributes["complete_from_source"] is True
    assert events[0]["attributes"]["external_provider_path_required_for_later_inspection"] is False
    assert str(rollout) not in json.dumps(events[0], ensure_ascii=False, sort_keys=True)

    accumulator = GraphAccumulator(
        session_id="codex-preview-test",
        source_path=tmp_path / "events.jsonl",
    )
    accumulator.apply(events[0])
    graph = accumulator.to_dict()
    entries = conversation_record_entries(graph, store.run_root)
    assert len(entries) == 1
    preview = entries[0]["conversation_preview"]
    assert preview["agent_path"] == "/root/nightfood_b"
    assert preview["agent_nickname"] == "Banach"
    assert any(
        message["sender"] == "/root/nightfood_a"
        and message["recipient"] == "/root/nightfood_b"
        and message["content_state"] == "provider_encrypted"
        for message in preview["messages"]
    )
    assert any(
        message["recipient"] == "/root" and message["content_state"] == "provider_encrypted"
        for message in preview["messages"]
    )
    assert any(
        message["phase"] == "final_answer"
        and message["text"] == "已與顧問 A 收斂：首選小李子清粥小菜，備案東引小吃店。"
        for message in preview["messages"]
    )

    viewer = write_graph_html(graph, store.run_root / "viewer.html")
    html = viewer.read_text(encoding="utf-8")
    assert "/root/nightfood_b" in html
    assert "Banach" in html
    assert "已與顧問 A 收斂：首選小李子清粥小菜，備案東引小吃店。" in html
    assert "Provider-encrypted payload" in html


def test_codex_visibility_uses_canonical_root_identity() -> None:
    event = _codex_trace_visibility_event("2026-08-28T00:00:00Z")

    assert event["source"] == {
        "type": "agent",
        "id": "agent:OpenAI Codex",
        "name": "OpenAI Codex",
        "attributes": {"provider": "codex"},
    }
    assert event["relation"] == "DECLARES_AGENT_TRACE_VISIBILITY"
    assert event["target"]["id"] == "agent-trace-capability:codex"
