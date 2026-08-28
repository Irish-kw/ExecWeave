from __future__ import annotations

import hashlib
import json
from pathlib import Path

from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import codex_conversation_archive_events


def test_codex_archive_preserves_complete_rollout_bytes(
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
                "content": [{"type": "output_text", "text": "先整理宵夜候選。"}],
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
                        "type": "encrypted_content",
                        "encrypted_content": "opaque-provider-ciphertext",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-08-28T00:00:03Z",
            "ordinal": 3,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "首選小李子清粥小菜。"}],
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
        timestamp="2026-08-28T00:00:04Z",
    )

    assert len(events) == 1
    target = events[0]["target"]
    attributes = target["attributes"]
    archived = store.run_root / attributes["path"]
    assert archived.read_bytes() == payload
    assert attributes["size_bytes"] == len(payload)
    assert attributes["sha256"] == hashlib.sha256(payload).hexdigest()
    assert attributes["complete_from_source"] is True
    assert events[0]["attributes"]["external_provider_path_required_for_later_inspection"] is False
